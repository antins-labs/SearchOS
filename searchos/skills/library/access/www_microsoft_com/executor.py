"""
Microsoft Investor Relations Access Skill

Provides access to Microsoft's investor relations data including:
- Annual reports (1996-2025)
- Quarterly earnings data (income statements, balance sheets, cash flows, metrics)
- Stock quote information
- Press releases

No official JSON API exists; all data is extracted from HTML pages.
"""

import asyncio
import re
from typing import Any
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.microsoft.com"

# Microsoft stock instrument ID for MSN Finance API
MSFT_INSTRUMENT_ID = "a1xzim"
FINANCE_API_KEY = "i8vZtQebr4UMX6pS8lHoqEk5IxB2oHnx2zxmqBjIaT"


async def fetch_html(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except Exception as e:
        return 0, str(e)


def parse_financial_table(html: str) -> list[dict]:
    """Parse financial data tables from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    results = []
    
    for table in tables:
        rows = table.find_all("tr")
        table_data = []
        headers = []
        
        for row_idx, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            cell_values = []
            for cell in cells:
                # Clean up the text
                text = cell.get_text(strip=True)
                text = re.sub(r'\s+', ' ', text)
                # Remove GAAP taxonomy prefixes
                text = re.sub(r'^us-gaap:[^\s]+\s*', '', text)
                cell_values.append(text)
            
            if row_idx == 0:
                headers = cell_values
            else:
                if any(v for v in cell_values):  # Skip empty rows
                    table_data.append(cell_values)
        
        if table_data:
            results.append({
                "headers": headers,
                "rows": table_data
            })
    
    return results


def format_table_as_dict(tables: list[dict]) -> list[dict]:
    """Convert table data to list of dictionaries."""
    results = []
    for table in tables:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    key = headers[i] if headers[i] else f"col_{i}"
                else:
                    key = f"col_{i}"
                row_dict[key] = value
            if row_dict:
                results.append(row_dict)
    
    return results


async def get_annual_reports(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get list of available annual reports."""
    url = f"{BASE_URL}/en-us/investor/annual-reports"
    status, html = await fetch_html(session, url)
    
    if status != 200:
        return {"error": f"Failed to fetch annual reports page: {status}", "status": status}
    
    soup = BeautifulSoup(html, "html.parser")
    reports = []
    
    # Find all annual report links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match pattern /ar{YY}/ where YY is 2 digits
        match = re.search(r'/ar(\d{2})/', href)
        if match:
            year_short = match.group(1)
            year = int(year_short)
            full_year = 2000 + year if year < 90 else 1900 + year
            
            title = link.get("title", "") or link.get_text(strip=True)
            is_download = "download" in href.lower()
            
            reports.append({
                "year": full_year,
                "year_short": year_short,
                "type": "download" if is_download else "view",
                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                "title": title
            })
    
    # Group by year
    grouped = {}
    for r in reports:
        year = r["year"]
        if year not in grouped:
            grouped[year] = {"year": year, "view_url": None, "download_url": None}
        if r["type"] == "download":
            grouped[year]["download_url"] = r["url"]
        else:
            grouped[year]["view_url"] = r["url"]
    
    # Convert to sorted list
    result = sorted(grouped.values(), key=lambda x: x["year"], reverse=True)
    
    return {
        "success": True,
        "count": len(result),
        "annual_reports": result
    }


async def get_annual_report_detail(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get details for a specific annual report year."""
    year = params.get("year")
    if not year:
        return {"error": "Missing required parameter: year"}
    
    year_short = str(year)[-2:]
    url = f"{BASE_URL}/investor/reports/ar{year_short}/index.html"
    
    status, html = await fetch_html(session, url)
    if status != 200:
        return {"error": f"Annual report for year {year} not found", "status": status}
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract any downloadable files mentioned
    downloads = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if href.endswith((".pdf", ".doc", ".docx", ".xlsx")):
            downloads.append({
                "url": href if href.startswith("http") else f"{BASE_URL}{href}",
                "text": link.get_text(strip=True)
            })
    
    # Get page title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else f"Microsoft {year} Annual Report"
    
    return {
        "success": True,
        "year": year,
        "title": title,
        "view_url": url,
        "download_url": f"{BASE_URL}/investor/reports/ar{year_short}/download-center/",
        "downloads": downloads
    }


async def get_earnings(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get earnings data for a specific fiscal year and quarter."""
    fiscal_year = params.get("fiscal_year")
    quarter = params.get("quarter")
    section = params.get("section", "press-release-webcast")
    
    if not fiscal_year or not quarter:
        return {"error": "Missing required parameters: fiscal_year and quarter"}
    
    # Validate quarter
    quarter = int(quarter)
    if quarter not in [1, 2, 3, 4]:
        return {"error": "quarter must be 1, 2, 3, or 4"}
    
    fiscal_year = int(fiscal_year)
    
    valid_sections = [
        "press-release-webcast",
        "income-statements",
        "comprehensive-income",
        "balance-sheets",
        "cash-flows",
        "segment-revenues",
        "performance",
        "metrics",
        "productivity-and-business-processes-performance",
        "intelligent-cloud-performance",
        "more-personal-computing-performance"
    ]
    
    if section not in valid_sections:
        return {"error": f"Invalid section. Must be one of: {', '.join(valid_sections)}"}
    
    url = f"{BASE_URL}/en-us/Investor/earnings/FY-{fiscal_year}-Q{quarter}/{section}"
    
    status, html = await fetch_html(session, url)
    if status != 200:
        return {"error": f"Earnings data not found for FY{fiscal_year} Q{quarter}", "status": status, "url": url}
    
    # Parse table data
    tables = parse_financial_table(html)
    
    # Get main content
    soup = BeautifulSoup(html, "html.parser")
    
    # Get title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    
    # Get press release text for press-release-webcast section
    press_release_content = None
    if section == "press-release-webcast":
        content_div = soup.find("div", class_="pressrelease-class") or soup.find("div", id="pressreleasecontent")
        if content_div:
            press_release_content = content_div.get_text(strip=True, separator=" ")
            press_release_content = re.sub(r'\s+', ' ', press_release_content)[:5000]
    
    result = {
        "success": True,
        "fiscal_year": fiscal_year,
        "quarter": quarter,
        "section": section,
        "url": url,
        "title": title
    }
    
    if tables:
        result["tables"] = tables
        result["tables_formatted"] = format_table_as_dict(tables)
    
    if press_release_content:
        result["press_release_content"] = press_release_content
    
    return result


async def get_current_quarter(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get the most recent earnings quarter."""
    # Microsoft's fiscal year starts in July
    # Q1: Jul-Sep, Q2: Oct-Dec, Q3: Jan-Mar, Q4: Apr-Jun
    now = datetime.now()
    
    # Determine current fiscal year and quarter
    if now.month >= 7:
        fiscal_year = now.year + 1
        months_offset = now.month - 7
    else:
        fiscal_year = now.year
        months_offset = now.month + 5
    
    current_quarter = (months_offset // 3) + 1
    if current_quarter > 4:
        current_quarter = 4
    
    return {
        "success": True,
        "current_fiscal_year": fiscal_year,
        "current_quarter": current_quarter,
        "note": "Microsoft's fiscal year starts in July. Q1: Jul-Sep, Q2: Oct-Dec, Q3: Jan-Mar, Q4: Apr-Jun"
    }


async def get_latest_earnings(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get the latest available earnings data by trying recent quarters."""
    quarter_info = await get_current_quarter(session, params)
    fy = quarter_info["current_fiscal_year"]
    q = quarter_info["current_quarter"]
    
    # Try current and previous quarters until we find one
    for offset in range(8):  # Try up to 8 quarters back
        test_q = q - offset
        test_fy = fy
        while test_q < 1:
            test_q += 4
            test_fy -= 1
        
        result = await get_earnings(session, {
            "fiscal_year": test_fy,
            "quarter": test_q,
            "section": params.get("section", "press-release-webcast")
        })
        
        if result.get("success"):
            result["is_latest"] = True
            return result
    
    return {"error": "Could not find recent earnings data"}


async def list_available_earnings(session: aiohttp.ClientSession, params: dict) -> dict:
    """List available earnings sections for a fiscal year/quarter."""
    fiscal_year = params.get("fiscal_year")
    quarter = params.get("quarter")
    
    if not fiscal_year or not quarter:
        return {"error": "Missing required parameters: fiscal_year and quarter"}
    
    sections = [
        {"name": "press-release-webcast", "description": "Press release and webcast information"},
        {"name": "income-statements", "description": "Income statement data"},
        {"name": "comprehensive-income", "description": "Comprehensive income data"},
        {"name": "balance-sheets", "description": "Balance sheet data"},
        {"name": "cash-flows", "description": "Cash flow statement data"},
        {"name": "segment-revenues", "description": "Segment revenue breakdown"},
        {"name": "performance", "description": "Performance metrics"},
        {"name": "metrics", "description": "Key business metrics"},
        {"name": "productivity-and-business-processes-performance", "description": "Productivity & Business Processes segment"},
        {"name": "intelligent-cloud-performance", "description": "Intelligent Cloud segment"},
        {"name": "more-personal-computing-performance", "description": "More Personal Computing segment"}
    ]
    
    base_url = f"{BASE_URL}/en-us/Investor/earnings/FY-{fiscal_year}-Q{quarter}"
    
    return {
        "success": True,
        "fiscal_year": fiscal_year,
        "quarter": quarter,
        "sections": [
            {**s, "url": f"{base_url}/{s['name']}"} for s in sections
        ]
    }


async def get_stock_quote(session: aiohttp.ClientSession, params: dict) -> dict:
    """Get current stock quote for Microsoft (MSFT)."""
    # Use the MSN Finance API
    url = f"https://api.msn.com/Finance/Quotes"
    params_api = {
        "apikey": FINANCE_API_KEY,
        "activityId": "MicrosoftIRSkill",
        "ocid": "MSIR",
        "cm": "en-us",
        "it": "edgeid",
        "scn": "AL_APP_ANON",
        "ids": MSFT_INSTRUMENT_ID
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.microsoft.com/",
        "Accept": "application/json"
    }
    
    try:
        async with session.get(url, params=params_api, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status != 200:
                return {"error": f"Failed to fetch stock quote: {response.status}"}
            
            data = await response.json()
            
            if "value" in data and len(data["value"]) > 0:
                quote = data["value"][0]
                return {
                    "success": True,
                    "symbol": quote.get("symbol", "MSFT"),
                    "company_name": quote.get("displayName", "Microsoft Corporation"),
                    "price": quote.get("price"),
                    "price_change": quote.get("priceChange"),
                    "price_change_percent": quote.get("priceChangePercent"),
                    "price_open": quote.get("priceDayOpen"),
                    "price_high": quote.get("priceDayHigh"),
                    "price_low": quote.get("priceDayLow"),
                    "price_previous_close": quote.get("pricePreviousClose"),
                    "volume": quote.get("accumulatedVolume"),
                    "average_volume": quote.get("averageVolume"),
                    "market_cap": quote.get("marketCap"),
                    "pe_ratio": quote.get("peRatio"),
                    "fifty_two_week_high": quote.get("price52wHigh"),
                    "fifty_two_week_low": quote.get("price52wLow"),
                    "dividend_yield_percent": quote.get("yieldPercent"),
                    "exchange": quote.get("exchangeName", "Nasdaq"),
                    "currency": quote.get("currency", "USD"),
                    "last_updated": quote.get("timeLastUpdated")
                }
            else:
                return {"error": "No quote data returned"}
                
    except Exception as e:
        return {"error": f"Failed to fetch stock quote: {str(e)}"}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Microsoft Investor Relations access skill.
    
    Parameters:
        params: Dictionary containing:
            - function: The function to call (required)
            - Additional parameters specific to each function
    
    Functions:
        - annual_reports: List all available annual reports
        - annual_report_detail: Get details for a specific year (requires: year)
        - earnings: Get earnings data (requires: fiscal_year, quarter; optional: section)
        - current_quarter: Get info about current fiscal year/quarter
        - latest_earnings: Get most recent available earnings (optional: section)
        - list_earnings_sections: List available sections for a quarter (requires: fiscal_year, quarter)
        - stock_quote: Get current MSFT stock quote
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == "annual_reports":
            return await get_annual_reports(session, params)
        elif function == "annual_report_detail":
            return await get_annual_report_detail(session, params)
        elif function == "earnings":
            return await get_earnings(session, params)
        elif function == "current_quarter":
            return await get_current_quarter(session, params)
        elif function == "latest_earnings":
            return await get_latest_earnings(session, params)
        elif function == "list_earnings_sections":
            return await list_available_earnings(session, params)
        elif function == "stock_quote":
            return await get_stock_quote(session, params)
        else:
            return {"error": f"Unknown function: {function}. Available functions: annual_reports, annual_report_detail, earnings, current_quarter, latest_earnings, list_earnings_sections, stock_quote"}


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        print("Testing annual_reports...")
        result = await execute({"function": "annual_reports"})
        print(json.dumps(result, indent=2)[:1000])
        print("\n" + "="*80 + "\n")
        
        print("Testing current_quarter...")
        result = await execute({"function": "current_quarter"})
        print(json.dumps(result, indent=2))
        print("\n" + "="*80 + "\n")
        
        print("Testing latest_earnings...")
        result = await execute({"function": "latest_earnings", "section": "metrics"})
        print(json.dumps(result, indent=2)[:2000])
        print("\n" + "="*80 + "\n")
        
        print("Testing earnings (FY-2025-Q3)...")
        result = await execute({"function": "earnings", "fiscal_year": 2025, "quarter": 3, "section": "income-statements"})
        print(json.dumps(result, indent=2)[:2000])
        print("\n" + "="*80 + "\n")
        
        print("Testing stock_quote...")
        result = await execute({"function": "stock_quote"})
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())