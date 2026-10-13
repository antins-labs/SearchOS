"""
Netflix Investor Relations Access Skill

Provides access to Netflix's SEC filings and annual reports from ir.netflix.net.
Uses the Q4 platform API endpoints for structured data retrieval.

Note: This site uses Cloudflare protection, so Playwright is used for reliable access.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Optional
from playwright.async_api import async_playwright


# API Configuration
BASE_URL = "https://ir.netflix.net"
API_KEY = "BF185719B0464B3CB809D23926182246"


def _convert_json_date(date_str: Optional[str]) -> Optional[str]:
    """Convert .NET JSON date /Date(timestamp-offset)/ to ISO format."""
    if not date_str:
        return None
    
    match = re.match(r'/Date\((\d+)([+-]\d{4})\)/', date_str)
    if match:
        timestamp_ms = int(match.group(1))
        dt = datetime.utcfromtimestamp(timestamp_ms / 1000.0)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return date_str


def _normalize_filing(filing: dict) -> dict:
    """Normalize a filing record for consistent output."""
    documents = []
    for doc in filing.get('DocumentList', []):
        documents.append({
            'document_type': doc.get('DocumentType'),
            'document_id': doc.get('FilingDocumentId'),
            'url': doc.get('Url') if doc.get('Url') else None,
            'create_date': _convert_json_date(doc.get('CreateDate')),
        })
    
    return {
        'filing_id': filing.get('FilingId'),
        'edgar_filing_id': filing.get('EdgarFilingId'),
        'form_type': filing.get('FilingTypeMnemonic'),
        'form_description': filing.get('FilingDescription'),
        'filing_date': filing.get('FilingDate'),
        'received_date': filing.get('ReceivedDate'),
        'filing_agent': filing.get('FilingAgentName'),
        'report_person_name': filing.get('ReportPersonName'),
        'detail_page': f"{BASE_URL}{filing.get('LinkToDetailPage', '')}" if filing.get('LinkToDetailPage') else None,
        'documents': documents,
    }


def _normalize_event(event: dict) -> dict:
    """Normalize an event record for consistent output."""
    return {
        'event_id': event.get('EventId'),
        'title': event.get('Title'),
        'start_date': event.get('StartDate'),
        'end_date': event.get('EndDate'),
        'location': event.get('Location'),
        'is_webcast': event.get('IsWebcast'),
        'webcast_link': event.get('WebCastLink'),
        'tags': event.get('TagsList', []),
        'detail_page': f"{BASE_URL}{event.get('LinkToDetailPage', '')}" if event.get('LinkToDetailPage') else None,
        'seo_name': event.get('SeoName'),
    }


async def _fetch_json(url: str) -> dict:
    """Fetch JSON data using Playwright to bypass Cloudflare."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            # Navigate to the API endpoint
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Get the page content
            content = await page.content()
            
            # Extract JSON from <pre> tag if present (browser wraps JSON in <pre>)
            if '<pre' in content:
                pre = await page.query_selector('pre')
                if pre:
                    text = await pre.inner_text()
                    data = json.loads(text)
                    return data
            else:
                # Try parsing content directly
                try:
                    return json.loads(content)
                except:
                    return {'error': 'Failed to parse response', 'content_preview': content[:500]}
        except Exception as e:
            return {'error': f'Request failed: {str(e)}'}
        finally:
            await browser.close()


async def get_sec_filings_years(ctx: Any = None) -> dict:
    """Get available years for SEC filings."""
    url = f"{BASE_URL}/feed/SECFiling.svc/GetEdgarFilingYearList"
    params = {
        'apiKey': API_KEY,
        'LanguageId': 1,
        'exchange': 'CIK',
        'symbol': '0001065280',
        'formGroupIdList': '',
        'excludeNoDocuments': 'true',
        'tagList': '',
    }
    
    full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    data = await _fetch_json(full_url)
    
    if 'error' in data:
        return {'years': [], 'error': data['error']}
    
    years = data.get('GetEdgarFilingYearListResult', [])
    return {'years': years}


async def get_sec_filings(year: Optional[int] = None, form_type: Optional[str] = None, page: int = 0, page_size: int = 100, ctx: Any = None) -> dict:
    """
    Get SEC filings with optional filtering.
    
    Args:
        year: Year to filter by (e.g., 2024). Use -1 for all years, or None for all years.
        form_type: Form type to filter by (e.g., '10-K', '8-K', '4').
        page: Page number (0-indexed).
        page_size: Number of results per page. Use -1 for all results.
    """
    url = f"{BASE_URL}/feed/SECFiling.svc/GetEdgarFilingList"
    params = {
        'apiKey': API_KEY,
        'LanguageId': 1,
        'exchange': 'CIK',
        'symbol': '0001065280',
        'formGroupIdList': '',
        'excludeNoDocuments': 'true',
        'pageSize': str(page_size),
        'pageNumber': str(page),
        'tagList': '',
        'includeTags': 'true',
        'year': str(year) if year is not None else '-1',
        'excludeSelection': '1',
    }
    
    full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    data = await _fetch_json(full_url)
    
    if 'error' in data:
        return {'filings': [], 'total_count': 0, 'error': data['error']}
    
    filings = data.get('GetEdgarFilingListResult', [])
    
    # Filter by form type if specified
    if form_type:
        form_type_upper = form_type.upper()
        filings = [f for f in filings if f.get('FilingTypeMnemonic', '').upper() == form_type_upper]
    
    normalized = [_normalize_filing(f) for f in filings]
    
    return {
        'filings': normalized,
        'total_count': len(normalized),
        'year_filter': year,
        'form_type_filter': form_type,
    }


async def get_event_years(ctx: Any = None) -> dict:
    """Get available years for annual reports/events."""
    url = f"{BASE_URL}/feed/Event.svc/GetEventYearList"
    params = {
        'apiKey': API_KEY,
        'LanguageId': 1,
        'eventSelection': 3,
        'eventDateFilter': 3,
        'includeFinancialReports': 'true',
        'includePresentations': 'true',
        'includePressReleases': 'true',
        'sortOperator': 1,
        'tagList': 'annual',
    }
    
    full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    data = await _fetch_json(full_url)
    
    if 'error' in data:
        return {'years': [], 'error': data['error']}
    
    years = data.get('GetEventYearListResult', [])
    return {'years': years}


async def get_annual_reports(year: Optional[int] = None, ctx: Any = None) -> dict:
    """
    Get annual reports and proxy statements.
    
    Args:
        year: Year to filter by. Use -1 for all years, or None for all years.
    """
    url = f"{BASE_URL}/feed/Event.svc/GetEventList"
    params = {
        'apiKey': API_KEY,
        'LanguageId': 1,
        'eventSelection': 3,
        'eventDateFilter': 3,
        'includeFinancialReports': 'true',
        'includePresentations': 'true',
        'includePressReleases': 'true',
        'sortOperator': 1,
        'pageSize': -1,
        'pageNumber': 0,
        'tagList': 'annual',
        'includeTags': 'true',
        'year': year if year is not None else -1,
        'excludeSelection': 1,
    }
    
    full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    data = await _fetch_json(full_url)
    
    if 'error' in data:
        return {'reports': [], 'total_count': 0, 'error': data['error']}
    
    events = data.get('GetEventListResult', [])
    normalized = [_normalize_event(e) for e in events]
    
    return {
        'reports': normalized,
        'total_count': len(normalized),
        'year_filter': year,
    }


async def search_filings(query: Optional[str] = None, year: Optional[int] = None, form_type: Optional[str] = None, limit: int = 50, ctx: Any = None) -> dict:
    """
    Search SEC filings with optional text search and filters.
    
    Args:
        query: Text to search in filing description or person name.
        year: Year to filter by.
        form_type: Form type to filter by (e.g., '10-K', '8-K', '4').
        limit: Maximum number of results.
    """
    # Get filings
    result = await get_sec_filings(year=year, form_type=form_type, page_size=-1)
    
    if 'error' in result:
        return result
    
    filings = result['filings']
    
    # Text search if query provided
    if query:
        query_lower = query.lower()
        filtered = []
        for f in filings:
            # Safely get string values, converting None to empty string
            form_desc = (f.get('form_description') or '').lower()
            person_name = (f.get('report_person_name') or '').lower()
            filing_agent = (f.get('filing_agent') or '').lower()
            form_t = (f.get('form_type') or '').lower()
            
            searchable = ' '.join([form_desc, person_name, filing_agent, form_t])
            if query_lower in searchable:
                filtered.append(f)
        filings = filtered
    
    return {
        'filings': filings[:limit],
        'total_count': len(filings),
        'query': query,
        'year_filter': year,
        'form_type_filter': form_type,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the Netflix IR skill.
    
    Dispatches based on params['function']:
        - get_sec_filings_years: Get available years for SEC filings
        - get_sec_filings: Get SEC filings (optionally filtered by year/form)
        - get_event_years: Get available years for annual reports
        - get_annual_reports: Get annual reports and proxy statements
        - search_filings: Search SEC filings with text query and filters
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'available_functions': [
                'get_sec_filings_years',
                'get_sec_filings',
                'get_event_years',
                'get_annual_reports',
                'search_filings',
            ],
        }
    
    if function == 'get_sec_filings_years':
        return await get_sec_filings_years(ctx)
    
    elif function == 'get_sec_filings':
        return await get_sec_filings(
            year=params.get('year'),
            form_type=params.get('form_type'),
            page=params.get('page', 0),
            page_size=params.get('page_size', 100),
            ctx=ctx,
        )
    
    elif function == 'get_event_years':
        return await get_event_years(ctx)
    
    elif function == 'get_annual_reports':
        return await get_annual_reports(
            year=params.get('year'),
            ctx=ctx,
        )
    
    elif function == 'search_filings':
        return await search_filings(
            query=params.get('query'),
            year=params.get('year'),
            form_type=params.get('form_type'),
            limit=params.get('limit', 50),
            ctx=ctx,
        )
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_sec_filings_years',
                'get_sec_filings',
                'get_event_years',
                'get_annual_reports',
                'search_filings',
            ],
        }