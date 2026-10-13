"""
Executor for MCT Data Service Portal (sjfw.mct.gov.cn)
Extracts tourism-related data from the Ministry of Culture and Tourism data service.

Supported data types:
- 10: 国家5A级旅游景区 (National 5A Tourist Attractions)
- 11: 五星级旅游饭店 (Five-star Hotels)
- 54: 国家级旅游度假区 (National Tourist Resorts)
- 135: 国家级滑雪旅游度假地 (National Ski Tourist Resorts)
- 138: 国家级旅游休闲街区 (National Tourist Leisure Districts)
- 143: 国家工业旅游示范基地 (National Industrial Tourism Demo Bases)
"""

import asyncio
import json
import re
from typing import Any

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from playwright.async_api import async_playwright

# Data type mapping
DATA_TYPES = {
    10: "国家5A级旅游景区",
    11: "五星级旅游饭店",
    54: "国家级旅游度假区",
    135: "国家级滑雪旅游度假地",
    138: "国家级旅游休闲街区",
    143: "国家工业旅游示范基地"
}

BASE_URL = "https://sjfw.mct.gov.cn/site/dataservice/rural"


def parse_nuxt_html(html: str) -> list[dict]:
    """
    Parse the NUXT data directly from HTML content.
    
    The page embeds data in a minified format:
    L[0]={province:{code:M,name:"北京",sort:1000},list:[{id:34005,grade:a,batch:c,code:a,name:"...",...}]}
    
    The function parameters map to values passed at the end:
    (a,b,c,d,e,f,...) => (null,null,0,"2021-12-20 13:34:40","2024","2023",...)
    where a=null, b=null, c=0, d="2021-12-20 13:34:40", e="2024", f="2023", etc.
    """
    
    # Extract function parameters (the values at the end)
    # Pattern: function(a,b,c,...){...}(null,null,0,"2021-12-20 13:34:40","2024",...)
    params_match = re.search(
        r'window\.__NUXT__=\(function\([^)]+\)\{.*?\}\)\((.*?)\);?\s*</script>',
        html, re.DOTALL
    )
    
    if not params_match:
        return []
    
    args_str = params_match.group(1)
    
    # Parse the arguments
    args = []
    current = ""
    in_quotes = False
    quote_char = None
    bracket_depth = 0
    
    for char in args_str:
        if char in '"\'':
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
            current += char
        elif char == '[':
            bracket_depth += 1
            current += char
        elif char == ']':
            bracket_depth -= 1
            current += char
        elif char == ',' and not in_quotes and bracket_depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += char
    
    if current.strip():
        args.append(current.strip())
    
    # Convert args to dictionary mapping variable names to values
    # Variable names: a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z,A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z,_,$,aa,ab,ac,ad,...
    var_names = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_") + ['$'] + ['aa', 'ab', 'ac', 'ad']
    arg_values = {}
    
    for i, arg in enumerate(args):
        if i < len(var_names):
            var_name = var_names[i]
            if arg == 'null':
                arg_values[var_name] = None
            elif arg == 'undefined':
                arg_values[var_name] = None
            elif arg.startswith('"') or arg.startswith("'"):
                arg_values[var_name] = arg[1:-1] if len(arg) > 1 else ""
            elif arg.isdigit() or (arg.startswith('-') and arg[1:].isdigit()):
                arg_values[var_name] = int(arg)
            else:
                try:
                    arg_values[var_name] = float(arg)
                except ValueError:
                    arg_values[var_name] = arg
    
    # Parse province data from L[] assignments
    # L[0]={province:{code:M,name:"北京",sort:1000},list:[{...},{...}]}
    provinces = []
    
    # Find all L[...]=... assignments
    l_pattern = r'L\[(\d+)\]=\{province:\{code:([^,]+),name:"([^"]+)",sort:(\d+)\},list:\[(.*?)\]\}'
    
    for match in re.finditer(l_pattern, html, re.DOTALL):
        idx = int(match.group(1))
        code_var = match.group(2)
        province_name = match.group(3)
        sort = int(match.group(4))
        list_str = match.group(5)
        
        # Resolve code value
        code = arg_values.get(code_var, code_var)
        if isinstance(code, str) and code.isdigit():
            code = int(code)
        
        # Parse list items
        items = []
        # Pattern for items: {id:34005,grade:a,batch:c,code:a,name:"...",province:M,place:a,year:e,created_at:"..."}
        item_pattern = r'\{id:(\d+),grade:([^,]+),batch:(\d+),code:([^,]*),name:"([^"]+)",province:([^,]+),place:([^,]*),year:([^,]+),created_at:"([^"]+)"\}'
        
        for item_match in re.finditer(item_pattern, list_str):
            item_id = int(item_match.group(1))
            grade_var = item_match.group(2)
            batch = int(item_match.group(3))
            code_var_item = item_match.group(4)
            name = item_match.group(5)
            province_var = item_match.group(6)
            place_var = item_match.group(7)
            year_var = item_match.group(8)
            created_at = item_match.group(9)
            
            # Resolve variable references
            grade = arg_values.get(grade_var, '') if grade_var in arg_values and arg_values[grade_var] is not None else ''
            
            code_val = arg_values.get(code_var_item, '') if code_var_item in arg_values and arg_values[code_var_item] is not None else ''
            
            place = arg_values.get(place_var, '') if place_var in arg_values and arg_values[place_var] is not None else ''
            
            year = arg_values.get(year_var, year_var.strip('"')) if year_var in arg_values else year_var.strip('"')
            
            province_code = arg_values.get(province_var, province_var)
            if isinstance(province_code, str) and province_code.isdigit():
                province_code = int(province_code)
            
            items.append({
                'id': item_id,
                'grade': grade,
                'batch': batch,
                'code': code_val,
                'name': name,
                'province': province_code,
                'place': place,
                'year': year,
                'created_at': created_at
            })
        
        provinces.append({
            'province': {'code': code, 'name': province_name, 'sort': sort},
            'list': items
        })
    
    return provinces


async def fetch_data_fast(type_id: int) -> dict[str, Any]:
    """
    Fast data fetch using aiohttp and HTML parsing.
    """
    if not HAS_AIOHTTP:
        return None
    
    url = f"{BASE_URL}?type={type_id}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    return None
                
                html = await resp.text()
                provinces = parse_nuxt_html(html)
                
                if not provinces:
                    return None
                
                # Flatten the data
                result = []
                for prov in provinces:
                    province_info = prov.get('province', {})
                    for item in prov.get('list', []):
                        result.append({
                            'id': item.get('id'),
                            'name': item.get('name', ''),
                            'province_code': province_info.get('code'),
                            'province_name': province_info.get('name', ''),
                            'year': item.get('year', ''),
                            'grade': item.get('grade', ''),
                            'code': item.get('code', ''),
                            'place': item.get('place', ''),
                            'created_at': item.get('created_at', '')
                        })
                
                return {
                    'success': True,
                    'type_id': type_id,
                    'type_name': DATA_TYPES.get(type_id, ''),
                    'url': url,
                    'total_count': len(result),
                    'data': result
                }
    
    except Exception:
        return None


async def fetch_data_browser(type_id: int) -> dict[str, Any]:
    """
    Fetch data for a specific type using Playwright browser automation.
    
    Args:
        type_id: The data type ID (10, 11, 54, 135, 138, or 143)
    
    Returns:
        dict with 'success', 'data', and optional 'error' keys
    """
    url = f"{BASE_URL}?type={type_id}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)  # Wait for NUXT data to be fully loaded
                
                # Extract the NUXT data
                nuxt_data = await page.evaluate("() => window.__NUXT__")
                
                if not nuxt_data:
                    return {
                        "success": False,
                        "error": "Failed to extract NUXT data from page"
                    }
                
                # Parse the data structure
                result = {
                    "success": True,
                    "type_id": type_id,
                    "type_name": DATA_TYPES.get(type_id, ""),
                    "url": url,
                    "data": []
                }
                
                # Extract province data
                if nuxt_data.get("data") and len(nuxt_data["data"]) > 0:
                    provinces_data = nuxt_data["data"][0].get("Provinces", [])
                    
                    if len(provinces_data) > 1:
                        provinces = provinces_data[1]  # First element is empty object
                        
                        total_count = 0
                        for province_entry in provinces:
                            if isinstance(province_entry, dict):
                                province_info = province_entry.get("province", {})
                                items = province_entry.get("list", [])
                                
                                for item in items:
                                    entry = {
                                        "id": item.get("id"),
                                        "name": item.get("name", ""),
                                        "province_code": province_info.get("code"),
                                        "province_name": province_info.get("name", ""),
                                        "year": item.get("year", ""),
                                        "grade": item.get("grade", "") if item.get("grade") else "",
                                        "code": item.get("code", "") if item.get("code") else "",
                                        "place": item.get("place", "") if item.get("place") else "",
                                        "created_at": item.get("created_at", "")
                                    }
                                    result["data"].append(entry)
                                    total_count += 1
                        
                        result["total_count"] = total_count
                
                return result
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out",
            "type_id": type_id,
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "type_id": type_id,
            "url": url
        }


async def fetch_data(type_id: int) -> dict[str, Any]:
    """
    Fetch data for a specific type, trying fast method first.
    """
    if type_id not in DATA_TYPES:
        return {
            "success": False,
            "error": f"Invalid type_id: {type_id}. Valid types: {list(DATA_TYPES.keys())}"
        }
    
    # Try fast method first
    if HAS_AIOHTTP:
        result = await fetch_data_fast(type_id)
        if result and result.get('success'):
            return result
    
    # Fall back to browser method
    return await fetch_data_browser(type_id)


async def list_data_types() -> dict[str, Any]:
    """
    List all available data types with their names.
    
    Returns:
        dict with available data types
    """
    return {
        "success": True,
        "data_types": [
            {"type_id": k, "name": v} for k, v in DATA_TYPES.items()
        ]
    }


async def get_data_count(type_id: int) -> dict[str, Any]:
    """
    Get the count of entries for a specific data type without fetching all data.
    
    Args:
        type_id: The data type ID
    
    Returns:
        dict with count information
    """
    if type_id not in DATA_TYPES:
        return {
            "success": False,
            "error": f"Invalid type_id: {type_id}. Valid types: {list(DATA_TYPES.keys())}"
        }
    
    result = await fetch_data(type_id)
    
    if result["success"]:
        return {
            "success": True,
            "type_id": type_id,
            "type_name": DATA_TYPES[type_id],
            "total_count": result.get("total_count", 0)
        }
    else:
        return result


async def filter_by_province(type_id: int, province_name: str) -> dict[str, Any]:
    """
    Fetch data filtered by province name.
    
    Args:
        type_id: The data type ID
        province_name: The province name to filter by (e.g., "北京", "上海")
    
    Returns:
        dict with filtered data
    """
    result = await fetch_data(type_id)
    
    if not result["success"]:
        return result
    
    filtered_data = [
        entry for entry in result["data"]
        if entry.get("province_name", "").startswith(province_name)
    ]
    
    return {
        "success": True,
        "type_id": type_id,
        "type_name": DATA_TYPES[type_id],
        "province_filter": province_name,
        "total_count": len(filtered_data),
        "data": filtered_data
    }


async def search_by_name(type_id: int, name_keyword: str) -> dict[str, Any]:
    """
    Search data by name keyword.
    
    Args:
        type_id: The data type ID
        name_keyword: The keyword to search in names
    
    Returns:
        dict with matching entries
    """
    result = await fetch_data(type_id)
    
    if not result["success"]:
        return result
    
    matching_data = [
        entry for entry in result["data"]
        if name_keyword.lower() in entry.get("name", "").lower()
    ]
    
    return {
        "success": True,
        "type_id": type_id,
        "type_name": DATA_TYPES[type_id],
        "search_keyword": name_keyword,
        "total_count": len(matching_data),
        "data": matching_data
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on the 'function' parameter:
    - list_types: List all available data types
    - fetch: Fetch all data for a specific type
    - count: Get count of entries for a type
    - filter_province: Filter data by province
    - search: Search data by name keyword
    
    Args:
        params: Dictionary containing 'function' and required parameters
        ctx: Context (unused)
    
    Returns:
        Result dictionary with 'success' and data/error
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function"
        }
    
    if function == "list_types":
        return await list_data_types()
    
    elif function == "fetch":
        type_id = params.get("type_id")
        if type_id is None:
            return {
                "success": False,
                "error": "Missing required parameter: type_id"
            }
        
        try:
            type_id = int(type_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid type_id: {type_id}. Must be an integer."
            }
        
        return await fetch_data(type_id)
    
    elif function == "count":
        type_id = params.get("type_id")
        if type_id is None:
            return {
                "success": False,
                "error": "Missing required parameter: type_id"
            }
        
        try:
            type_id = int(type_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid type_id: {type_id}. Must be an integer."
            }
        
        return await get_data_count(type_id)
    
    elif function == "filter_province":
        type_id = params.get("type_id")
        province_name = params.get("province_name")
        
        if type_id is None:
            return {
                "success": False,
                "error": "Missing required parameter: type_id"
            }
        if not province_name:
            return {
                "success": False,
                "error": "Missing required parameter: province_name"
            }
        
        try:
            type_id = int(type_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid type_id: {type_id}. Must be an integer."
            }
        
        return await filter_by_province(type_id, province_name)
    
    elif function == "search":
        type_id = params.get("type_id")
        name_keyword = params.get("name_keyword")
        
        if type_id is None:
            return {
                "success": False,
                "error": "Missing required parameter: type_id"
            }
        if not name_keyword:
            return {
                "success": False,
                "error": "Missing required parameter: name_keyword"
            }
        
        try:
            type_id = int(type_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid type_id: {type_id}. Must be an integer."
            }
        
        return await search_by_name(type_id, name_keyword)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Valid functions: list_types, fetch, count, filter_province, search"
        }