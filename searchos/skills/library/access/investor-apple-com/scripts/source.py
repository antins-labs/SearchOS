"""
Apple Investor Relations Access Skill

Provides structured access to Apple's investor relations data including:
- Financial reports (quarterly and annual)
- SEC filings
- Stock quotes and historical data
- Events and earnings calls
- Press releases and presentations

Uses Playwright browser automation to bypass Cloudflare protection.
"""

import asyncio
import json
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class AppleInvestorClient:
    """Client for Apple Investor Relations API via browser automation."""
    
    API_KEY = "BF185719B0464B3CB809D23926182246"
    BASE_URL = "https://investor.apple.com/feed"
    MAIN_PAGE = "https://investor.apple.com/investor-relations/default.aspx"
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Initialize browser and navigate to main page to establish session."""
        if self._initialized:
            return
        
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # Navigate to main page to establish session and bypass Cloudflare
        await self.page.goto(self.MAIN_PAGE, wait_until='networkidle', timeout=60000)
        await self.page.wait_for_timeout(2000)
        self._initialized = True
    
    async def close(self):
        """Close browser resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.context = None
            self.page = None
            self._initialized = False
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()
    
    async def _fetch_api(self, endpoint: str, params: dict) -> dict:
        """Fetch data from API endpoint."""
        await self._ensure_initialized()
        
        param_parts = []
        for k, v in params.items():
            if isinstance(v, list):
                for item in v:
                    param_parts.append(f"{k}={item}")
            else:
                param_parts.append(f"{k}={v}")
        param_str = "&".join(param_parts)
        
        url = f"{self.BASE_URL}/{endpoint}?{param_str}"
        
        response = await self.page.evaluate(f'''
            async () => {{
                const resp = await fetch("{url}", {{
                    method: "GET",
                    credentials: "include"
                }});
                const text = await resp.text();
                return {{ status: resp.status, body: text }};
            }}
        ''')
        
        if response['status'] != 200:
            return {"error": f"HTTP {response['status']}", "body": response['body'][:500]}
        
        try:
            return json.loads(response['body'])
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "body": response['body'][:500]}
    
    async def get_financial_reports(
        self,
        report_type: str = "quarterly",
        year: int = -1,
        page_size: int = 50,
        page_number: int = 0
    ) -> dict:
        """
        Get financial reports (quarterly or annual).
        
        Args:
            report_type: "quarterly" or "annual"
            year: Year to filter (-1 for all years)
            page_size: Number of results (-1 for all)
            page_number: Page number for pagination
        """
        if report_type == "quarterly":
            report_types = "First Quarter|Second Quarter|Third Quarter|Fourth Quarter"
            sub_types = ["First Quarter", "Second Quarter", "Third Quarter", "Fourth Quarter"]
        else:
            report_types = "Annual Report"
            sub_types = ["Annual Report"]
        
        params = {
            "apiKey": self.API_KEY,
            "LanguageId": 1,
            "reportTypes": report_types,
            "reportSubType[]": sub_types,
            "reportSubTypeList[]": sub_types,
            "pageSize": page_size,
            "pageNumber": page_number,
            "tagList": "",
            "includeTags": "true",
            "year": year,
            "excludeSelection": 1
        }
        
        result = await self._fetch_api("FinancialReport.svc/GetFinancialReportList", params)
        
        if "error" in result:
            return result
        
        reports = result.get("GetFinancialReportListResult", [])
        
        # Extract and structure the documents
        structured_reports = []
        for report in reports:
            structured_report = {
                "report_id": report.get("ReportId"),
                "title": report.get("ReportTitle"),
                "year": report.get("ReportYear"),
                "sub_type": report.get("ReportSubType"),
                "date": report.get("ReportDate"),
                "documents": []
            }
            
            for doc in report.get("Documents", []):
                structured_report["documents"].append({
                    "title": doc.get("DocumentTitle"),
                    "category": doc.get("DocumentCategory"),
                    "type": doc.get("DocumentType"),
                    "file_type": doc.get("DocumentFileType"),
                    "file_size": doc.get("DocumentFileSize"),
                    "url": doc.get("DocumentPath")
                })
            
            structured_reports.append(structured_report)
        
        return {
            "success": True,
            "count": len(structured_reports),
            "report_type": report_type,
            "year": year if year > 0 else "all",
            "reports": structured_reports
        }
    
    async def get_financial_report_years(self, report_type: str = "annual") -> dict:
        """Get available years for financial reports."""
        if report_type == "annual":
            report_types = "Annual Report"
            sub_types = ["Annual Report"]
        else:
            report_types = "First Quarter|Second Quarter|Third Quarter|Fourth Quarter"
            sub_types = ["First Quarter", "Second Quarter", "Third Quarter", "Fourth Quarter"]
        
        params = {
            "apiKey": self.API_KEY,
            "LanguageId": 1,
            "reportTypes": report_types,
            "reportSubType[]": sub_types,
            "reportSubTypeList[]": sub_types,
            "tagList": ""
        }
        
        result = await self._fetch_api("FinancialReport.svc/GetFinancialReportYearList", params)
        
        if "error" in result:
            return result
        
        years = result.get("GetFinancialReportYearListResult", [])
        
        return {
            "success": True,
            "report_type": report_type,
            "years": years
        }
    
    async def get_sec_filings(
        self,
        year: int = -1,
        filing_type: str = "",
        page_size: int = 50,
        page_number: int = 0
    ) -> dict:
        """
        Get SEC filings.
        
        Args:
            year: Year to filter (-1 for all years)
            filing_type: Filing type filter (e.g., "10-K", "10-Q", "8-K", "4")
            page_size: Number of results (-1 for all)
            page_number: Page number for pagination
        """
        params = {
            "LanguageId": 1,
            "exchange": "CIK",
            "symbol": "0000320193",  # Apple's CIK number
            "formGroupIdList": "",
            "filingTypeList": filing_type,
            "excludeNoDocuments": "true",
            "includeHtmlDocument": "false",
            "pageSize": page_size,
            "pageNumber": page_number,
            "tagList": "",
            "includeTags": "true",
            "year": year,
            "excludeSelection": 1
        }
        
        result = await self._fetch_api("SECFiling.svc/GetEdgarFilingList", params)
        
        if "error" in result:
            return result
        
        filings = result.get("GetEdgarFilingListResult", [])
        
        # Structure filings
        structured_filings = []
        for filing in filings:
            structured_filing = {
                "filing_id": filing.get("FilingId"),
                "filing_date": filing.get("FilingDate"),
                "received_date": filing.get("ReceivedDate"),
                "description": filing.get("FilingDescription"),
                "form_type": filing.get("FilingTypeMnemonic"),
                "report_person": filing.get("ReportPersonName"),
                "filing_agent": filing.get("FilingAgentName"),
                "documents": []
            }
            
            for doc in filing.get("DocumentList", []):
                structured_filing["documents"].append({
                    "type": doc.get("DocumentType"),
                    "url": doc.get("Url") if doc.get("Url") else None,
                    "document_id": doc.get("FilingDocumentId")
                })
            
            structured_filings.append(structured_filing)
        
        return {
            "success": True,
            "count": len(structured_filings),
            "year": year if year > 0 else "all",
            "filing_type": filing_type if filing_type else "all",
            "filings": structured_filings
        }
    
    async def get_sec_filing_years(self) -> dict:
        """Get available years for SEC filings."""
        params = {
            "LanguageId": 1,
            "exchange": "CIK",
            "symbol": "0000320193",
            "formGroupIdList": "",
            "filingTypeList": "",
            "excludeNoDocuments": "true",
            "includeHtmlDocument": "false",
            "tagList": ""
        }
        
        result = await self._fetch_api("SECFiling.svc/GetEdgarFilingYearList", params)
        
        if "error" in result:
            return result
        
        years = result.get("GetEdgarFilingYearListResult", [])
        
        return {
            "success": True,
            "years": years
        }
    
    async def get_stock_quote(self) -> dict:
        """Get current stock quote for AAPL."""
        params = {
            "apiKey": self.API_KEY,
            "exchange": "XNAS",
            "symbol": "AAPL",
            "pageSize": 1
        }
        
        result = await self._fetch_api("StockQuote.svc/GetFullStockQuoteList", params)
        
        if "error" in result:
            return result
        
        quotes = result.get("GetFullStockQuoteListResult", [])
        
        if not quotes:
            return {"success": False, "error": "No quote data available"}
        
        quote = quotes[0]
        
        return {
            "success": True,
            "quote": {
                "symbol": quote.get("Symbol"),
                "company_name": quote.get("CompanyName"),
                "exchange": quote.get("Exchange"),
                "price": quote.get("TradePrice"),
                "change": quote.get("Change"),
                "percent_change": quote.get("PercChange"),
                "previous_close": quote.get("PreviousClose"),
                "open": quote.get("Open"),
                "high": quote.get("High"),
                "low": quote.get("Low"),
                "high_52_week": quote.get("High52"),
                "low_52_week": quote.get("Low52"),
                "volume": quote.get("Volume"),
                "trade_date": quote.get("TradeDate"),
                "pe_ratio": quote.get("PeRatio"),
                "eps": quote.get("EPS"),
                "dividend_yield": quote.get("DivYield"),
                "market_cap": quote.get("MarketCap")
            }
        }
    
    async def get_stock_history(self, days: int = 30) -> dict:
        """
        Get historical stock prices.
        
        Args:
            days: Number of trading days to retrieve (max 3000)
        """
        params = {
            "apiKey": self.API_KEY,
            "pageSize": min(days, 3000),
            "exchange": "XNAS",
            "symbol": "AAPL"
        }
        
        result = await self._fetch_api("StockQuote.svc/GetStockQuoteHistoricalList", params)
        
        if "error" in result:
            return result
        
        quotes = result.get("GetStockQuoteHistoricalListResult", [])
        
        structured_quotes = []
        for quote in quotes:
            structured_quotes.append({
                "date": quote.get("HistoricalDate"),
                "open": quote.get("Open"),
                "high": quote.get("High"),
                "low": quote.get("Low"),
                "close": quote.get("Last"),
                "volume": quote.get("Volume")
            })
        
        return {
            "success": True,
            "count": len(structured_quotes),
            "quotes": structured_quotes
        }
    
    async def get_events(
        self,
        year: int = -1,
        include_financial_reports: bool = True,
        include_presentations: bool = True,
        include_press_releases: bool = True,
        page_size: int = 20,
        page_number: int = 0
    ) -> dict:
        """
        Get investor events (earnings calls, presentations, press releases).
        
        Args:
            year: Year to filter (-1 for all years)
            include_financial_reports: Include financial report events
            include_presentations: Include presentation events
            include_press_releases: Include press release events
            page_size: Number of results (-1 for all)
            page_number: Page number for pagination
        """
        params = {
            "apiKey": self.API_KEY,
            "LanguageId": 1,
            "eventSelection": 3,
            "eventDateFilter": 3,
            "includeFinancialReports": str(include_financial_reports).lower(),
            "includePresentations": str(include_presentations).lower(),
            "includePressReleases": str(include_press_releases).lower(),
            "sortOperator": 1,
            "pageSize": page_size,
            "pageNumber": page_number,
            "tagList": "",
            "includeTags": "true",
            "year": year,
            "excludeSelection": 1
        }
        
        result = await self._fetch_api("Event.svc/GetEventList", params)
        
        if "error" in result:
            return result
        
        events = result.get("GetEventListResult", [])
        
        structured_events = []
        for event in events:
            structured_event = {
                "event_id": event.get("EventId"),
                "title": event.get("Title"),
                "start_date": event.get("StartDate"),
                "end_date": event.get("EndDate"),
                "location": event.get("Location"),
                "is_webcast": event.get("IsWebcast"),
                "webcast_link": event.get("WebCastLink"),
                "link": event.get("LinkToDetailPage"),
                "tags": event.get("TagsList", []),
                "body_preview": event.get("Body", "")[:200] if event.get("Body") else None,
                "attachments": []
            }
            
            for att in event.get("Attachments", []):
                structured_event["attachments"].append({
                    "title": att.get("Title"),
                    "type": att.get("Type"),
                    "url": att.get("Url"),
                    "document_type": att.get("DocumentType")
                })
            
            structured_events.append(structured_event)
        
        return {
            "success": True,
            "count": len(structured_events),
            "year": year if year > 0 else "all",
            "events": structured_events
        }
    
    async def get_event_years(self) -> dict:
        """Get available years for events."""
        params = {
            "apiKey": self.API_KEY,
            "LanguageId": 1,
            "eventSelection": 3,
            "eventDateFilter": 3,
            "includeFinancialReports": "true",
            "includePresentations": "true",
            "includePressReleases": "true",
            "sortOperator": 1,
            "tagList": ""
        }
        
        result = await self._fetch_api("Event.svc/GetEventYearList", params)
        
        if "error" in result:
            return result
        
        years = result.get("GetEventYearListResult", [])
        
        return {
            "success": True,
            "years": years
        }
    
    async def get_additional_reports(self, year: int = -1) -> dict:
        """Get additional reports (supplementary financial documents)."""
        params = {
            "apiKey": self.API_KEY,
            "LanguageId": 1,
            "assetType": "Additional Reports",
            "pageSize": -1,
            "pageNumber": 0,
            "tagList": "",
            "includeTags": "true",
            "year": year,
            "excludeSelection": 1
        }
        
        result = await self._fetch_api("ContentAsset.svc/GetContentAssetList", params)
        
        if "error" in result:
            return result
        
        assets = result.get("GetContentAssetListResult", [])
        
        structured_assets = []
        for asset in assets:
            structured_assets.append({
                "asset_id": asset.get("ContentAssetId"),
                "title": asset.get("Title"),
                "description": asset.get("Description"),
                "file_type": asset.get("FileType"),
                "file_size": asset.get("FileSize"),
                "url": asset.get("FilePath"),
                "thumbnail": asset.get("ThumbnailPath"),
                "tags": asset.get("TagsList", [])
            })
        
        return {
            "success": True,
            "count": len(structured_assets),
            "year": year if year > 0 else "all",
            "reports": structured_assets
        }


# Global client instance
_client: Optional[AppleInvestorClient] = None


async def get_client() -> AppleInvestorClient:
    """Get or create the global client instance."""
    global _client
    if _client is None:
        _client = AppleInvestorClient()
    return _client


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Apple Investor Relations API requests.
    
    Args:
        params: Dictionary containing:
            - function: One of:
                - "get_financial_reports": Get quarterly/annual financial reports
                - "get_financial_report_years": Get available years for reports
                - "get_sec_filings": Get SEC filings (10-K, 10-Q, 8-K, etc.)
                - "get_sec_filing_years": Get available years for SEC filings
                - "get_stock_quote": Get current AAPL stock quote
                - "get_stock_history": Get historical stock prices
                - "get_events": Get investor events (earnings calls, presentations)
                - "get_event_years": Get available years for events
                - "get_additional_reports": Get supplementary financial documents
            - Additional parameters specific to each function:
                - report_type: "quarterly" or "annual" (default: "quarterly")
                - year: Year filter (-1 for all)
                - days: Number of days for stock history (default: 30)
                - filing_type: SEC filing type filter
                - page_size: Results per page
                - page_number: Page number
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with success status and requested data or error message.
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "available_functions": [
                "get_financial_reports",
                "get_financial_report_years",
                "get_sec_filings",
                "get_sec_filing_years",
                "get_stock_quote",
                "get_stock_history",
                "get_events",
                "get_event_years",
                "get_additional_reports"
            ]
        }
    
    client = await get_client()
    
    try:
        if function == "get_financial_reports":
            report_type = params.get("report_type", "quarterly")
            year = params.get("year", -1)
            page_size = params.get("page_size", 50)
            page_number = params.get("page_number", 0)
            return await client.get_financial_reports(report_type, year, page_size, page_number)
        
        elif function == "get_financial_report_years":
            report_type = params.get("report_type", "annual")
            return await client.get_financial_report_years(report_type)
        
        elif function == "get_sec_filings":
            year = params.get("year", -1)
            filing_type = params.get("filing_type", "")
            page_size = params.get("page_size", 50)
            page_number = params.get("page_number", 0)
            return await client.get_sec_filings(year, filing_type, page_size, page_number)
        
        elif function == "get_sec_filing_years":
            return await client.get_sec_filing_years()
        
        elif function == "get_stock_quote":
            return await client.get_stock_quote()
        
        elif function == "get_stock_history":
            days = params.get("days", 30)
            return await client.get_stock_history(days)
        
        elif function == "get_events":
            year = params.get("year", -1)
            include_financial_reports = params.get("include_financial_reports", True)
            include_presentations = params.get("include_presentations", True)
            include_press_releases = params.get("include_press_releases", True)
            page_size = params.get("page_size", 20)
            page_number = params.get("page_number", 0)
            return await client.get_events(
                year, include_financial_reports, include_presentations, 
                include_press_releases, page_size, page_number
            )
        
        elif function == "get_event_years":
            return await client.get_event_years()
        
        elif function == "get_additional_reports":
            year = params.get("year", -1)
            return await client.get_additional_reports(year)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_financial_reports",
                    "get_financial_report_years",
                    "get_sec_filings",
                    "get_sec_filing_years",
                    "get_stock_quote",
                    "get_stock_history",
                    "get_events",
                    "get_event_years",
                    "get_additional_reports"
                ]
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception: {str(e)}"
        }


# For cleanup when module is unloaded
async def cleanup():
    """Clean up browser resources."""
    global _client
    if _client:
        await _client.close()
        _client = None