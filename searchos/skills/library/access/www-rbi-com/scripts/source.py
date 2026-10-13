"""
RBI (Restaurant Brands International) Annual Reports Access Skill

Provides programmatic access to RBI's annual reports and financial documents
via their internal FinancialReport API.

Functions:
- list_reports: Get all annual reports with document details
- list_years: Get available report years
- filter_reports: Filter reports by year or document type
"""

import asyncio
from typing import Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def _fetch_api_data(page: Page, endpoint: str, params: dict) -> dict:
    """Fetch data from RBI's FinancialReport API via browser context"""
    base_url = "https://www.rbi.com/feed/FinancialReport.svc"
    api_key = "BF185719B0464B3CB809D23926182246"
    
    # Add API key to params
    all_params = {'apiKey': api_key, **params}
    
    # Build URL
    param_str = '&'.join([f'{k}={v}' for k, v in all_params.items()])
    full_url = f"{base_url}/{endpoint}?{param_str}"
    
    # Execute fetch in browser context
    result = await page.evaluate(f'''
        async () => {{
            try {{
                const response = await fetch("{full_url}", {{
                    method: 'GET',
                    credentials: 'include',
                    headers: {{
                        'Accept': 'application/json',
                    }}
                }});
                if (!response.ok) {{
                    return {{ error: 'HTTP ' + response.status, status: response.status }};
                }}
                const data = await response.json();
                return {{ data: data, status: response.status }};
            }} catch (e) {{
                return {{ error: e.message }};
            }}
        }}
    ''')
    
    if 'error' in result:
        return {'error': result['error'], 'success': False}
    
    return {'data': result.get('data', {}), 'success': True}


async def _ensure_browser_session(page: Page, base_url: str = "https://www.rbi.com/English/investors/annual-reports/default.aspx"):
    """Ensure we have a valid browser session by navigating to the page"""
    try:
        await page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
        return True
    except Exception as e:
        return False


def _normalize_report(report: dict) -> dict:
    """Normalize report data structure"""
    documents = []
    for doc in report.get('Documents', []):
        documents.append({
            'id': doc.get('DocumentId'),
            'title': doc.get('DocumentTitle'),
            'category': doc.get('DocumentCategory'),
            'type': doc.get('DocumentFileType'),
            'size': doc.get('DocumentFileSize'),
            'url': doc.get('DocumentPath'),
            'thumbnail': doc.get('ThumbnailPath'),
        })
    
    return {
        'id': report.get('ReportId'),
        'title': report.get('ReportTitle'),
        'year': report.get('ReportYear'),
        'date': report.get('ReportDate'),
        'sub_type': report.get('ReportSubType'),
        'documents': documents,
    }


async def list_reports(params: dict, ctx: Any = None) -> dict:
    """
    List all annual reports with their associated documents.
    
    Parameters:
        params: Optional dict with:
            - year: Filter by specific year (integer)
            - include_documents: Include document details (default: True)
    
    Returns:
        dict with 'reports' list containing report details
    """
    year = params.get('year', -1)
    include_documents = params.get('include_documents', True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Establish session
            if not await _ensure_browser_session(page):
                return {
                    'success': False,
                    'error': 'Failed to establish browser session',
                    'reports': []
                }
            
            # Fetch reports
            api_params = {
                'LanguageId': 1,
                'reportTypes': 'Annual Report',
                'reportSubType[]': 'Annual Report',
                'reportSubTypeList[]': 'Annual Report',
                'pageSize': -1,
                'pageNumber': 0,
                'tagList': '',
                'includeTags': 'true',
                'year': year,
                'excludeSelection': 1
            }
            
            result = await _fetch_api_data(page, 'GetFinancialReportList', api_params)
            
            if not result.get('success'):
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'reports': []
                }
            
            reports_data = result.get('data', {}).get('GetFinancialReportListResult', [])
            
            reports = []
            for report in reports_data:
                normalized = _normalize_report(report)
                
                # Filter by year if specified
                if year != -1 and normalized.get('year') != year:
                    continue
                    
                if not include_documents:
                    normalized['documents'] = []
                    normalized['document_count'] = len(report.get('Documents', []))
                
                reports.append(normalized)
            
            return {
                'success': True,
                'count': len(reports),
                'reports': reports,
            }
            
        finally:
            await browser.close()


async def list_years(params: dict, ctx: Any = None) -> dict:
    """
    List available years for annual reports.
    
    Returns:
        dict with 'years' list
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Establish session
            if not await _ensure_browser_session(page):
                return {
                    'success': False,
                    'error': 'Failed to establish browser session',
                    'years': []
                }
            
            # Fetch years
            api_params = {
                'LanguageId': 1,
                'reportTypes': 'Annual Report',
                'reportSubType[]': 'Annual Report',
                'reportSubTypeList[]': 'Annual Report',
                'tagList': ''
            }
            
            result = await _fetch_api_data(page, 'GetFinancialReportYearList', api_params)
            
            if not result.get('success'):
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                    'years': []
                }
            
            years = result.get('data', {}).get('GetFinancialReportYearListResult', [])
            
            return {
                'success': True,
                'count': len(years),
                'years': years,
            }
            
        finally:
            await browser.close()


async def filter_reports(params: dict, ctx: Any = None) -> dict:
    """
    Filter and search reports by various criteria.
    
    Parameters:
        params: dict with:
            - year: Filter by year (optional)
            - document_type: Filter by document type (e.g., 'PDF', 'XLSX') (optional)
            - document_category: Filter by category (e.g., 'tenk', 'proxy') (optional)
            - search: Search in report/document titles (optional)
    
    Returns:
        dict with filtered 'reports' list
    """
    year = params.get('year')
    document_type = params.get('document_type', '').upper()
    document_category = params.get('document_category', '').lower()
    search = params.get('search', '').lower()
    
    # Get all reports first
    all_reports = await list_reports({'year': year if year else -1}, ctx)
    
    if not all_reports.get('success'):
        return all_reports
    
    filtered = []
    for report in all_reports.get('reports', []):
        # Filter documents if needed
        if document_type or document_category or search:
            matching_docs = []
            for doc in report.get('documents', []):
                match = True
                
                if document_type and doc.get('type', '').upper() != document_type:
                    match = False
                
                if document_category and document_category not in doc.get('category', '').lower():
                    match = False
                
                if search:
                    title_match = search in doc.get('title', '').lower()
                    report_match = search in report.get('title', '').lower()
                    if not (title_match or report_match):
                        match = False
                
                if match:
                    matching_docs.append(doc)
            
            if matching_docs or (search and search in report.get('title', '').lower()):
                report_copy = report.copy()
                report_copy['documents'] = matching_docs
                filtered.append(report_copy)
        else:
            filtered.append(report)
    
    return {
        'success': True,
        'count': len(filtered),
        'reports': filtered,
        'filters_applied': {
            'year': year,
            'document_type': document_type,
            'document_category': document_category,
            'search': search,
        }
    }


async def get_document_urls(params: dict, ctx: Any = None) -> dict:
    """
    Get download URLs for documents.
    
    Parameters:
        params: dict with:
            - year: Filter by year (optional)
            - document_type: Filter by type (optional)
    
    Returns:
        dict with 'documents' list containing titles, URLs, and metadata
    """
    year = params.get('year')
    document_type = params.get('document_type', '').upper()
    
    all_reports = await list_reports({'year': year if year else -1}, ctx)
    
    if not all_reports.get('success'):
        return all_reports
    
    documents = []
    for report in all_reports.get('reports', []):
        for doc in report.get('documents', []):
            if document_type and doc.get('type', '').upper() != document_type:
                continue
            
            documents.append({
                'report_year': report.get('year'),
                'report_title': report.get('title'),
                'title': doc.get('title'),
                'type': doc.get('type'),
                'size': doc.get('size'),
                'category': doc.get('category'),
                'url': doc.get('url'),
                'thumbnail': doc.get('thumbnail'),
            })
    
    return {
        'success': True,
        'count': len(documents),
        'documents': documents,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the RBI Annual Reports skill.
    
    Parameters:
        params: dict with:
            - function: One of 'list_reports', 'list_years', 'filter_reports', 'get_document_urls'
            - Additional parameters specific to each function
    
    Returns:
        dict with function result
    """
    function = params.get('function', 'list_reports')
    
    functions = {
        'list_reports': list_reports,
        'list_years': list_years,
        'filter_reports': filter_reports,
        'get_document_urls': get_document_urls,
    }
    
    if function not in functions:
        return {
            'success': False,
            'error': f"Unknown function: {function}. Valid functions: {list(functions.keys())}",
        }
    
    try:
        return await functions[function](params, ctx)
    except Exception as e:
        return {
            'success': False,
            'error': f"Execution error: {str(e)}",
        }