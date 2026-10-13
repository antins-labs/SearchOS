"""
SHFE (Shanghai Futures Exchange) Data Access Skill

Provides access to SHFE monthly trading statistics for futures and options.
The SHFE website uses WAF protection, but the .dat JSON API endpoints are 
directly accessible and provide comprehensive trading data.

Data Structure:
- Monthly futures data includes: trading statistics, turnover, volume, 
  delivery, open interest, and metal index data for all instruments
- Monthly options data includes: turnover, volume, open interest, exercise volume
- Product configuration: details about all traded products (futures and options)
"""

import aiohttp
import json
from datetime import datetime
from typing import Any, Optional

BASE_URL = "https://www.shfe.com.cn"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.shfe.com.cn/',
}


async def fetch_data(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch JSON data from SHFE API endpoint."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                text = await resp.text()
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"error": "Invalid JSON response", "status": resp.status, "url": url}
            else:
                return {"error": f"HTTP {resp.status}", "status": resp.status, "url": url}
    except aiohttp.ClientError as e:
        return {"error": str(e), "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


def parse_year_month(year: Optional[int], month: Optional[int]) -> tuple[int, int]:
    """
    Parse and validate year/month inputs.
    If not provided, defaults to previous month.
    """
    if year is None or month is None:
        now = datetime.now()
        # Default to previous month
        month = now.month - 1
        year = now.year
        if month <= 0:
            month = 12
            year -= 1
    
    year = int(year)
    month = int(month)
    
    if month < 1 or month > 12:
        raise ValueError(f"Invalid month: {month}. Must be 1-12.")
    
    if year < 2000 or year > datetime.now().year + 1:
        raise ValueError(f"Invalid year: {year}. Must be between 2000 and {datetime.now().year + 1}.")
    
    return year, month


async def get_monthly_futures_data(
    session: aiohttp.ClientSession,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> dict:
    """
    Get monthly futures trading statistics from SHFE.
    
    Returns comprehensive trading data including:
    - o_curtransaction: Per-instrument trading data
    - o_curturnover: Turnover statistics by product
    - o_curvolume: Volume statistics by product  
    - o_curdelivery: Delivery statistics
    - o_curopeninterest: Open interest statistics
    - o_curmetalindex: Metal index data
    """
    try:
        year, month = parse_year_month(year, month)
    except ValueError as e:
        return {"error": str(e)}
    
    url = f"{BASE_URL}/data/tradedata/future/monthdata/{year}{month:02d}monthvarietystatistics.dat"
    data = await fetch_data(session, url)
    
    if "error" in data:
        return data
    
    # Add metadata
    data['source_url'] = url
    data['data_type'] = 'monthly_futures'
    
    return data


async def get_monthly_options_data(
    session: aiohttp.ClientSession,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> dict:
    """
    Get monthly options trading statistics from SHFE.
    
    Returns trading data including:
    - o_curturnover: Turnover statistics by product
    - o_curvolume: Volume statistics by product
    - o_curopeninterest: Open interest statistics
    - o_curexercisevolume: Exercise volume statistics
    """
    try:
        year, month = parse_year_month(year, month)
    except ValueError as e:
        return {"error": str(e)}
    
    url = f"{BASE_URL}/data/tradedata/option/monthdata/{year}{month:02d}monthvarietystatistics.dat"
    data = await fetch_data(session, url)
    
    if "error" in data:
        return data
    
    data['source_url'] = url
    data['data_type'] = 'monthly_options'
    
    return data


async def get_product_config(session: aiohttp.ClientSession) -> dict:
    """
    Get product configuration data from SHFE.
    
    Returns detailed information about all traded products including:
    - Futures products (suffix _f): copper, aluminum, gold, etc.
    - Options products (suffix _o): options on various futures
    
    Each product includes: name, exchange, contract size, tick size, 
    trading currency, product type, etc.
    """
    url = f"{BASE_URL}/data/config/product_config.dat"
    data = await fetch_data(session, url)
    
    if "error" in data:
        return data
    
    data['source_url'] = url
    data['data_type'] = 'product_config'
    
    return data


async def get_report_config(session: aiohttp.ClientSession) -> dict:
    """
    Get report configuration from SHFE.
    
    Returns metadata about available report types including:
    - shfe_kx: Quick market reports
    - shfe_week: Weekly reports
    - shfe_month: Monthly reports
    - shfe_delivery: Delivery reports
    - shfe_dailystock: Daily stock reports
    - And many more report types
    """
    url = f"{BASE_URL}/data/config/report_config_cn.dat"
    data = await fetch_data(session, url)
    
    if "error" in data:
        return data
    
    data['source_url'] = url
    data['data_type'] = 'report_config'
    
    return data


async def get_web_config(session: aiohttp.ClientSession) -> dict:
    """
    Get web configuration from SHFE.
    
    Returns general web display configuration including:
    - Language settings
    - Currency names
    - Units and formatting rules
    """
    url = f"{BASE_URL}/data/config/web_config.dat"
    data = await fetch_data(session, url)
    
    if "error" in data:
        return data
    
    data['source_url'] = url
    data['data_type'] = 'web_config'
    
    return data


async def get_available_months(
    session: aiohttp.ClientSession,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None
) -> dict:
    """
    Discover available months with data by testing recent months.
    
    Tests monthly futures data endpoints to find which months have data available.
    """
    now = datetime.now()
    
    if end_year is None:
        end_year = now.year
    if start_year is None:
        start_year = end_year - 1  # Default to last 2 years
    
    start_year = int(start_year)
    end_year = int(end_year)
    
    available = []
    
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            # Skip future months
            if year > now.year or (year == now.year and month > now.month):
                continue
            
            url = f"{BASE_URL}/data/tradedata/future/monthdata/{year}{month:02d}monthvarietystatistics.dat"
            data = await fetch_data(session, url)
            
            if "error" not in data and data.get('o_code') == '0000':
                available.append({
                    "year": year,
                    "month": month,
                    "period": f"{year}{month:02d}",
                    "update_date": data.get('update_date'),
                    "instrument_count": len(data.get('o_curtransaction', [])),
                    "products": list(set(item.get('PRODUCT', '') for item in data.get('o_curtransaction', []) if item.get('PRODUCT')))
                })
    
    return {
        "available_months": available,
        "count": len(available),
        "data_type": "available_months"
    }


async def get_instrument_summary(
    session: aiohttp.ClientSession,
    year: Optional[int] = None,
    month: Optional[int] = None,
    product: Optional[str] = None
) -> dict:
    """
    Get a summary of instruments for a specific month.
    
    Useful for getting overview of trading activity without raw data.
    """
    try:
        year, month = parse_year_month(year, month)
    except ValueError as e:
        return {"error": str(e)}
    
    data = await get_monthly_futures_data(session, year, month)
    
    if "error" in data:
        return data
    
    transactions = data.get('o_curtransaction', [])
    
    # Filter by product if specified
    if product:
        product = product.lower()
        transactions = [t for t in transactions if t.get('PRODUCT', '').lower() == product]
    
    if not transactions:
        return {
            "error": f"No data found for product '{product}' in {year}-{month:02d}" if product else "No transaction data",
            "period": f"{year}{month:02d}"
        }
    
    # Compute summary statistics
    total_volume = sum(t.get('VOLUME', 0) for t in transactions)
    total_turnover = sum(t.get('TURNOVER', 0) for t in transactions)
    total_openinterest = sum(t.get('OPENINTEREST', 0) for t in transactions)
    
    products = {}
    for t in transactions:
        prod = t.get('PRODUCT', 'UNKNOWN')
        if prod not in products:
            products[prod] = {
                "product": prod,
                "instrument_count": 0,
                "volume": 0,
                "turnover": 0,
                "openinterest": 0
            }
        products[prod]["instrument_count"] += 1
        products[prod]["volume"] += t.get('VOLUME', 0)
        products[prod]["turnover"] += t.get('TURNOVER', 0)
        products[prod]["openinterest"] += t.get('OPENINTEREST', 0)
    
    return {
        "period": f"{year}{month:02d}",
        "report_date": data.get('report_date'),
        "update_date": data.get('update_date'),
        "total_instruments": len(transactions),
        "total_volume": total_volume,
        "total_turnover": total_turnover,
        "total_openinterest": total_openinterest,
        "products": list(products.values()),
        "product_count": len(products),
        "instruments": [
            {
                "instrument": t.get('INSTRUMENTID'),
                "product": t.get('PRODUCT'),
                "open": t.get('OPENPRICE'),
                "high": t.get('HIGHESTPRICE'),
                "low": t.get('LOWESTPRICE'),
                "close": t.get('CLOSEPRICE'),
                "settlement": t.get('SETTLEMENTPRICE'),
                "volume": t.get('VOLUME'),
                "turnover": t.get('TURNOVER'),
                "openinterest": t.get('OPENINTEREST'),
                "openinterest_chg": t.get('OPENINTERESTCHG'),
                "price_chg": t.get('PRICECHG')
            }
            for t in transactions
        ],
        "data_type": "instrument_summary"
    }


async def get_top_instruments(
    session: aiohttp.ClientSession,
    year: Optional[int] = None,
    month: Optional[int] = None,
    sort_by: str = "volume",
    limit: int = 10,
    product: Optional[str] = None
) -> dict:
    """
    Get top instruments ranked by specified metric.
    
    Sort options: volume, turnover, openinterest
    """
    try:
        year, month = parse_year_month(year, month)
    except ValueError as e:
        return {"error": str(e)}
    
    data = await get_monthly_futures_data(session, year, month)
    
    if "error" in data:
        return data
    
    transactions = data.get('o_curtransaction', [])
    
    # Filter by product if specified
    if product:
        product = product.lower()
        transactions = [t for t in transactions if t.get('PRODUCT', '').lower() == product]
    
    # Sort
    sort_fields = {
        "volume": "VOLUME",
        "turnover": "TURNOVER", 
        "openinterest": "OPENINTEREST"
    }
    
    sort_field = sort_fields.get(sort_by.lower(), "VOLUME")
    transactions.sort(key=lambda x: x.get(sort_field, 0), reverse=True)
    
    top = transactions[:int(limit)]
    
    return {
        "period": f"{year}{month:02d}",
        "report_date": data.get('report_date'),
        "sorted_by": sort_by,
        "top_instruments": [
            {
                "rank": i + 1,
                "instrument": t.get('INSTRUMENTID'),
                "product": t.get('PRODUCT'),
                "volume": t.get('VOLUME'),
                "turnover": t.get('TURNOVER'),
                "openinterest": t.get('OPENINTEREST'),
                "close": t.get('CLOSEPRICE'),
                "settlement": t.get('SETTLEMENTPRICE')
            }
            for i, t in enumerate(top)
        ],
        "data_type": "top_instruments"
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute SHFE data retrieval.
    
    Dispatches to appropriate function based on 'function' parameter.
    
    Available functions:
    - get_monthly_futures: Get monthly futures trading statistics
    - get_monthly_options: Get monthly options trading statistics  
    - get_product_config: Get product configuration
    - get_report_config: Get report configuration
    - get_web_config: Get web configuration
    - get_available_months: List months with available data
    - get_instrument_summary: Get instrument trading summary
    - get_top_instruments: Get top ranked instruments
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "error": "Missing required parameter 'function'",
            "available_functions": [
                "get_monthly_futures",
                "get_monthly_options",
                "get_product_config",
                "get_report_config",
                "get_web_config",
                "get_available_months",
                "get_instrument_summary",
                "get_top_instruments"
            ]
        }
    
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        
        if function == "get_monthly_futures":
            return await get_monthly_futures_data(
                session,
                year=params.get("year"),
                month=params.get("month")
            )
        
        elif function == "get_monthly_options":
            return await get_monthly_options_data(
                session,
                year=params.get("year"),
                month=params.get("month")
            )
        
        elif function == "get_product_config":
            return await get_product_config(session)
        
        elif function == "get_report_config":
            return await get_report_config(session)
        
        elif function == "get_web_config":
            return await get_web_config(session)
        
        elif function == "get_available_months":
            return await get_available_months(
                session,
                start_year=params.get("start_year"),
                end_year=params.get("end_year")
            )
        
        elif function == "get_instrument_summary":
            return await get_instrument_summary(
                session,
                year=params.get("year"),
                month=params.get("month"),
                product=params.get("product")
            )
        
        elif function == "get_top_instruments":
            return await get_top_instruments(
                session,
                year=params.get("year"),
                month=params.get("month"),
                sort_by=params.get("sort_by", "volume"),
                limit=params.get("limit", 10),
                product=params.get("product")
            )
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_monthly_futures",
                    "get_monthly_options",
                    "get_product_config",
                    "get_report_config",
                    "get_web_config",
                    "get_available_months",
                    "get_instrument_summary",
                    "get_top_instruments"
                ]
            }