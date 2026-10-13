"""
Sohu Auto Database Access Skill

Provides programmatic access to Sohu's automotive database at db.auto.sohu.com.
Direct API calls to portal.auto.sohu.com for car model data, pricing, sales,
and dealer information.
"""

import asyncio
import aiohttp
from typing import Any


BASE_URL = "https://portal.auto.sohu.com/aggr"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://db.auto.sohu.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


async def _fetch(session: aiohttp.ClientSession, endpoint: str) -> dict | list | None:
    """Fetch JSON data from API endpoint."""
    url = f"{BASE_URL}{endpoint}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content_type = resp.headers.get('content-type', '')
                if 'json' in content_type:
                    return await resp.json()
            return None
    except Exception as e:
        return {"error": str(e), "endpoint": endpoint}


async def get_model_stats(model_id: int) -> dict[str, Any]:
    """
    Get model information and sales statistics.
    
    Returns model details (name, brand, price range) and historical sales data
    including monthly retail sales and rankings.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/sales/v2/model/statistic?model_id={model_id}")
        if data is None:
            return {"error": "Model not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "data": data}


async def get_model_prices(model_ids: list[int]) -> dict[str, Any]:
    """
    Get price range for one or more car models.
    
    Returns local min/max prices for each model ID.
    """
    if not model_ids:
        return {"error": "model_ids list is required"}
    
    ids_str = ",".join(str(mid) for mid in model_ids)
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/price/model-prices?model_ids={ids_str}")
        if data is None:
            return {"error": "No price data found", "model_ids": model_ids}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_ids": model_ids, "prices": data}


async def get_trim_prices(model_id: int, city_code: str = "110100") -> dict[str, Any]:
    """
    Get trim-level pricing for a car model.
    
    Returns trim groups organized by year/status with guide prices and
    local dealer prices for a specific city.
    
    Common city codes:
    - 110100: Beijing
    - 310100: Shanghai
    - 330100: Hangzhou
    - 440100: Guangzhou
    - 440300: Shenzhen
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/price/trim-group-prices?model_id={model_id}&city_code={city_code}")
        if data is None:
            return {"error": "Trim prices not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "city_code": city_code, "trims": data}


async def get_city_prices(model_id: int) -> dict[str, Any]:
    """
    Get dealer prices across all cities for a car model.
    
    Returns prices organized by province and city with dealer counts
    and min/max prices.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/price/model-city-prices?model_id={model_id}")
        if data is None:
            return {"error": "City prices not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "cities": data}


async def get_dealer_prices(model_id: int, city_code: str = "110100", size: int = 999) -> dict[str, Any]:
    """
    Get dealer listing prices for a car model in a city.
    
    Returns dealer information including name, address, phone, location,
    and offered prices.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/price/model-dealer-prices?model_id={model_id}&city_code={city_code}&size={size}")
        if data is None:
            return {"error": "Dealer prices not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "city_code": city_code, "dealers": data}


async def get_model_news(model_id: int, limit: int = 10) -> dict[str, Any]:
    """
    Get news articles about a car model.
    
    Returns recent articles including title, brief, cover image,
    author info, and publication date.
    """
    limit = min(limit, 50)  # Cap at 50
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/media/news?model_id={model_id}&limit={limit}&last_score=")
        if data is None:
            return {"error": "News not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "articles": data}


async def get_competitor_ranking(model_id: int) -> dict[str, Any]:
    """
    Get same-segment competitor rankings for a car model.
    
    Returns competitors with evaluation scores across dimensions:
    looking (exterior), stuff (features), space, power, expense, overall.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/eval/same-level-rank?model_id={model_id}")
        if data is None:
            return {"error": "Competitor ranking not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "competitors": data}


async def get_related_trims(model_id: int, limit: int = 6) -> dict[str, Any]:
    """
    Get related/recommended trims for comparison.
    
    Returns similar car trims with pricing, year, and model info.
    """
    limit = min(limit, 20)
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"/model/related-trims?model_id={model_id}&limit={limit}")
        if data is None:
            return {"error": "Related trims not found", "model_id": model_id}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"model_id": model_id, "related": data}


async def get_hot_models() -> dict[str, Any]:
    """
    Get trending/hot car models.
    
    Returns list of currently popular car models on the platform.
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, "//search/hot-cars")
        if data is None:
            return {"error": "Hot models not found"}
        if isinstance(data, dict) and "error" in data:
            return data
        return {"hot_models": data}


async def get_full_model_info(model_id: int, city_code: str = "110100") -> dict[str, Any]:
    """
    Get comprehensive model information in one call.
    
    Aggregates basic info, pricing, trims, sales stats, and news.
    """
    async with aiohttp.ClientSession() as session:
        # Fetch multiple endpoints in parallel
        tasks = [
            _fetch(session, f"/sales/v2/model/statistic?model_id={model_id}"),
            _fetch(session, f"/price/model-prices?model_ids={model_id}"),
            _fetch(session, f"/price/trim-group-prices?model_id={model_id}&city_code={city_code}"),
            _fetch(session, f"/media/news?model_id={model_id}&limit=5&last_score="),
        ]
        
        results = await asyncio.gather(*tasks)
        
        stats_data, price_data, trim_data, news_data = results
        
        result = {"model_id": model_id, "city_code": city_code}
        
        if stats_data and not (isinstance(stats_data, dict) and "error" in stats_data):
            result["stats"] = stats_data
        
        if price_data and not (isinstance(price_data, dict) and "error" in price_data):
            result["prices"] = price_data
        
        if trim_data and not (isinstance(trim_data, dict) and "error" in trim_data):
            result["trims"] = trim_data
        
        if news_data and not (isinstance(news_data, dict) and "error" in news_data):
            result["news"] = news_data[:5] if isinstance(news_data, list) else news_data
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Sohu Auto API calls based on function parameter.
    
    Dispatches to the appropriate handler based on params["function"].
    
    Available functions:
    - get_model_stats: Model info + sales statistics (requires model_id)
    - get_model_prices: Price ranges for models (requires model_ids list)
    - get_trim_prices: Trim-level pricing (requires model_id, optional city_code)
    - get_city_prices: Prices across all cities (requires model_id)
    - get_dealer_prices: Dealer listings (requires model_id, optional city_code)
    - get_model_news: News articles (requires model_id, optional limit)
    - get_competitor_ranking: Competitor scores (requires model_id)
    - get_related_trims: Similar vehicles (requires model_id, optional limit)
    - get_hot_models: Trending models (no params required)
    - get_full_model_info: Comprehensive info (requires model_id, optional city_code)
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    try:
        if function == "get_model_stats":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            return await get_model_stats(int(model_id))
        
        elif function == "get_model_prices":
            model_ids = params.get("model_ids")
            if not model_ids:
                return {"error": "Missing required parameter: model_ids (list of integers)"}
            return await get_model_prices([int(mid) for mid in model_ids])
        
        elif function == "get_trim_prices":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            city_code = params.get("city_code", "110100")
            return await get_trim_prices(int(model_id), str(city_code))
        
        elif function == "get_city_prices":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            return await get_city_prices(int(model_id))
        
        elif function == "get_dealer_prices":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            city_code = params.get("city_code", "110100")
            size = params.get("size", 999)
            return await get_dealer_prices(int(model_id), str(city_code), int(size))
        
        elif function == "get_model_news":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            limit = params.get("limit", 10)
            return await get_model_news(int(model_id), int(limit))
        
        elif function == "get_competitor_ranking":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            return await get_competitor_ranking(int(model_id))
        
        elif function == "get_related_trims":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            limit = params.get("limit", 6)
            return await get_related_trims(int(model_id), int(limit))
        
        elif function == "get_hot_models":
            return await get_hot_models()
        
        elif function == "get_full_model_info":
            model_id = params.get("model_id")
            if not model_id:
                return {"error": "Missing required parameter: model_id"}
            city_code = params.get("city_code", "110100")
            return await get_full_model_info(int(model_id), str(city_code))
        
        else:
            return {"error": f"Unknown function: {function}"}
    
    except ValueError as e:
        return {"error": f"Invalid parameter value: {e}"}
    except Exception as e:
        return {"error": f"Execution failed: {str(e)}"}