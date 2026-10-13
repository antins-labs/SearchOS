"""
eBay Investor Relations Financial Data Access Skill

Provides access to eBay's investor relations financial data including:
- Financial reports (quarterly and annual) with downloadable documents
- Quarterly earnings press releases with parsed financial tables
- Financial metrics extraction (revenue, EPS, guidance, etc.)
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup
import httpx


# API Configuration
BASE_URL = "https://investors.ebayinc.com"
FINANCIAL_REPORTS_URL = f"{BASE_URL}/feed/FinancialReport.svc/GetFinancialReportList"
PRESS_RELEASE_URL = f"{BASE_URL}/Services/PressReleaseService.svc/GetPressReleaseList"
API_KEY = "BF185719B0464B3CB809D23926182246"
PR_CATEGORY_WORKFLOW_ID = "1cb807d2-208f-4bc3-9133-6a9ad45ac3b0"

# Request headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/json; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': BASE_URL,
    'Referer': f"{BASE_URL}/financial-information/financial-summary/default.aspx"
}


async def _http_get(client: httpx.AsyncClient, url: str, params: dict = None) -> dict:
    """Make GET request and return JSON response"""
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "details": str(e)}
    except Exception as e:
        return {"error": "Request failed", "details": str(e)}


async def _http_post(client: httpx.AsyncClient, url: str, json_data: dict) -> dict:
    """Make POST request and return JSON response"""
    try:
        resp = await client.post(url, json=json_data)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}", "details": str(e)}
    except Exception as e:
        return {"error": "Request failed", "details": str(e)}


async def _init_session(client: httpx.AsyncClient):
    """Initialize session by visiting main page"""
    try:
        await client.get(f"{BASE_URL}/financial-information/financial-summary/default.aspx")
        await asyncio.sleep(0.5)
    except:
        pass


def _parse_table(table) -> list:
    """Parse HTML table to list of rows"""
    rows = []
    for tr in table.find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        row_data = []
        for cell in cells:
            text = re.sub(r'\s+', ' ', cell.get_text(strip=True))
            row_data.append(text)
        if any(row_data):
            rows.append(row_data)
    return rows


def _extract_metrics_from_tables(tables: list) -> dict:
    """Extract key financial metrics from parsed tables"""
    metrics = {
        "income_statement": [],
        "balance_sheet": [],
        "guidance": [],
        "other_tables": []
    }
    
    for i, table_rows in enumerate(tables):
        if not table_rows:
            continue
        
        first_cell = table_rows[0][0].lower() if table_rows[0] else ""
        
        # Identify table type by content
        if any(keyword in first_cell for keyword in ['in millions', 'in billions']):
            # Check if it's guidance
            is_guidance = any('guidance' in ' '.join(row).lower() for row in table_rows[:3])
            
            if is_guidance:
                metrics['guidance'].append({
                    'table_index': i,
                    'data': table_rows
                })
            elif any(kw in ' '.join([r[0] for r in table_rows[:10]]).lower() for kw in ['revenue', 'net income', 'earnings per']):
                metrics['income_statement'].append({
                    'table_index': i,
                    'data': table_rows
                })
            elif any(kw in ' '.join([r[0] for r in table_rows[:15]]).lower() for kw in ['assets', 'liabilities', 'stockholders']):
                metrics['balance_sheet'].append({
                    'table_index': i,
                    'data': table_rows
                })
            else:
                metrics['other_tables'].append({
                    'table_index': i,
                    'data': table_rows
                })
        else:
            metrics['other_tables'].append({
                'table_index': i,
                'data': table_rows
            })
    
    return metrics


def _extract_key_figures(tables_data: list) -> dict:
    """Extract key numerical figures from tables"""
    figures = {}
    
    for table_rows in tables_data:
        for row in table_rows:
            if len(row) < 2:
                continue
            
            label = row[0].lower()
            row_str = ' '.join(row)
            
            # Revenue
            if 'net revenue' in label or label == 'revenue':
                match = re.search(r'\$[\d,.]+', row_str)
                if match:
                    figures['revenue'] = match.group()
            
            # Net income
            if 'net income' in label:
                match = re.search(r'\$[\d,.]+', row_str)
                if match:
                    figures['net_income'] = match.group()
            
            # EPS
            if 'earnings per diluted share' in label or 'diluted eps' in label:
                if 'gaap' in label:
                    match = re.search(r'\$[\d.]+', row_str)
                    if match:
                        figures['gaap_eps'] = match.group()
                elif 'non-gaap' in label:
                    match = re.search(r'\$[\d.]+', row_str)
                    if match:
                        figures['non_gaap_eps'] = match.group()
                else:
                    match = re.search(r'\$[\d.]+', row_str)
                    if match:
                        figures['eps'] = match.group()
            
            # GMV
            if 'gross merchandise volume' in label:
                match = re.search(r'\$[\d,.]+', row_str)
                if match:
                    figures['gmv'] = match.group()
    
    return figures


async def get_financial_reports(
    year: int = None,
    report_type: str = None,
    limit: int = 20
) -> dict:
    """
    Get list of financial reports (quarterly and annual earnings reports)
    
    Args:
        year: Filter by year (e.g., 2025). If None, returns all years.
        report_type: Filter by type: 'quarterly', 'annual', or None for all
        limit: Maximum number of reports to return (default 20)
    
    Returns:
        Dict with 'reports' list containing report metadata and download links
    """
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        await _init_session(client)
        
        params = {
            'apiKey': API_KEY,
            'includeTags': 'true',
            'tagList': '',
            'year': str(year) if year else '-1',
            'LanguageId': '1'
        }
        
        data = await _http_get(client, FINANCIAL_REPORTS_URL, params)
        
        if 'error' in data:
            return data
        
        reports = data.get('GetFinancialReportListResult', [])
        
        # Filter by report type
        if report_type:
            report_type_lower = report_type.lower()
            if report_type_lower == 'quarterly':
                reports = [r for r in reports if 'Quarter' in r.get('ReportSubType', '')]
            elif report_type_lower == 'annual':
                reports = [r for r in reports if 'Annual' in r.get('ReportSubType', '')]
        
        # Limit results
        reports = reports[:limit]
        
        # Structure the output
        result = {
            "total_returned": len(reports),
            "reports": []
        }
        
        for r in reports:
            report_info = {
                "title": r.get('ReportTitle'),
                "year": r.get('ReportYear'),
                "type": r.get('ReportSubType'),
                "documents": []
            }
            
            for doc in r.get('Documents', []):
                doc_info = {
                    "title": doc.get('DocumentTitle'),
                    "type": doc.get('DocumentFileType'),
                    "size": doc.get('DocumentFileSize'),
                    "category": doc.get('DocumentCategory'),
                    "url": doc.get('DocumentPath')
                }
                report_info['documents'].append(doc_info)
            
            result['reports'].append(report_info)
        
        return result


async def get_quarterly_earnings(
    quarters: int = 4,
    include_tables: bool = True
) -> dict:
    """
    Get quarterly earnings press releases with parsed financial tables
    
    Args:
        quarters: Number of recent quarters to retrieve (default 4)
        include_tables: Whether to include parsed table data (default True)
    
    Returns:
        Dict with quarterly earnings data including financial metrics
    """
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        await _init_session(client)
        
        payload = {
            "serviceDto": {
                "ViewType": "2",
                "ViewDate": "",
                "RevisionNumber": "1",
                "LanguageId": "1",
                "Signature": "",
                "ItemCount": quarters,
                "StartIndex": 0,
                "TagList": ["quarterly"],
                "IncludeTags": True
            },
            "pressReleaseSelection": 3,
            "pressReleaseBodyType": 2,
            "pressReleaseCategoryWorkflowId": PR_CATEGORY_WORKFLOW_ID,
            "year": -1
        }
        
        data = await _http_post(client, PRESS_RELEASE_URL, payload)
        
        if 'error' in data:
            return data
        
        press_releases = data.get('GetPressReleaseListResult', [])
        
        result = {
            "total_returned": len(press_releases),
            "quarterly_earnings": []
        }
        
        for pr in press_releases:
            earnings_data = {
                "headline": pr.get('Headline'),
                "date": pr.get('PressReleaseDate'),
                "url": f"{BASE_URL}/news/news-details/{pr.get('PressReleaseId', '')}/default.aspx",
            }
            
            if include_tables:
                body = pr.get('Body', '')
                soup = BeautifulSoup(body, 'html.parser')
                tables = soup.find_all('table')
                
                parsed_tables = [_parse_table(t) for t in tables]
                parsed_tables = [t for t in parsed_tables if t]  # Remove empty tables
                
                metrics = _extract_metrics_from_tables(parsed_tables)
                key_figures = _extract_key_figures(parsed_tables)
                
                earnings_data['table_count'] = len(parsed_tables)
                earnings_data['key_figures'] = key_figures
                earnings_data['tables'] = {
                    "income_statement": metrics['income_statement'],
                    "balance_sheet": metrics['balance_sheet'],
                    "guidance": metrics['guidance'],
                    "other": metrics['other_tables'][:3]  # Limit other tables
                }
            
            result['quarterly_earnings'].append(earnings_data)
        
        return result


async def parse_financial_statement(
    quarter: str = None,
    year: int = None,
    statement_type: str = "all"
) -> dict:
    """
    Parse specific financial statement from quarterly earnings
    
    Args:
        quarter: Quarter to parse (e.g., "Q1", "First Quarter"). If None, uses latest.
        year: Year to parse (e.g., 2025). If None, uses latest.
        statement_type: Type of statement: 'income', 'balance', 'guidance', 'all'
    
    Returns:
        Dict with parsed financial statement data
    """
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
        await _init_session(client)
        
        # Get the specific quarter's press release
        payload = {
            "serviceDto": {
                "ViewType": "2",
                "ViewDate": "",
                "RevisionNumber": "1",
                "LanguageId": "1",
                "Signature": "",
                "ItemCount": 10,
                "StartIndex": 0,
                "TagList": ["quarterly"],
                "IncludeTags": True
            },
            "pressReleaseSelection": 3,
            "pressReleaseBodyType": 2,
            "pressReleaseCategoryWorkflowId": PR_CATEGORY_WORKFLOW_ID,
            "year": year if year else -1
        }
        
        data = await _http_post(client, PRESS_RELEASE_URL, payload)
        
        if 'error' in data:
            return data
        
        press_releases = data.get('GetPressReleaseListResult', [])
        
        # Filter by quarter if specified
        if quarter:
            quarter_normalized = quarter.lower().replace('quarter', '').strip()
            quarter_variants = {
                'q1': ['first', 'q1'],
                'q2': ['second', 'q2'],
                'q3': ['third', 'q3'],
                'q4': ['fourth', 'q4'],
                'first': ['first', 'q1'],
                'second': ['second', 'q2'],
                'third': ['third', 'q3'],
                'fourth': ['fourth', 'q4']
            }
            
            search_terms = quarter_variants.get(quarter_normalized, [quarter_normalized])
            
            filtered = []
            for pr in press_releases:
                headline_lower = pr.get('Headline', '').lower()
                if any(term in headline_lower for term in search_terms):
                    filtered.append(pr)
            
            if filtered:
                press_releases = filtered
            elif press_releases:
                # Use latest if no match
                press_releases = [press_releases[0]]
        
        if not press_releases:
            return {"error": "No matching quarterly earnings found"}
        
        # Parse the first matching press release
        pr = press_releases[0]
        body = pr.get('Body', '')
        soup = BeautifulSoup(body, 'html.parser')
        tables = soup.find_all('table')
        
        parsed_tables = [_parse_table(t) for t in tables]
        parsed_tables = [t for t in parsed_tables if t]
        
        metrics = _extract_metrics_from_tables(parsed_tables)
        key_figures = _extract_key_figures(parsed_tables)
        
        result = {
            "headline": pr.get('Headline'),
            "date": pr.get('PressReleaseDate'),
            "key_figures": key_figures,
            "statements": {}
        }
        
        statement_type_lower = statement_type.lower()
        
        if statement_type_lower in ['income', 'all']:
            result['statements']['income_statement'] = metrics['income_statement']
        
        if statement_type_lower in ['balance', 'all']:
            result['statements']['balance_sheet'] = metrics['balance_sheet']
        
        if statement_type_lower in ['guidance', 'all']:
            result['statements']['guidance'] = metrics['guidance']
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution entry point
    
    Args:
        params: Dict with 'function' key specifying which function to call
        ctx: Optional context (unused)
    
    Returns:
        Dict with function results or error information
    """
    function = params.get('function')
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    try:
        if function == 'get_financial_reports':
            year = params.get('year')
            if year is not None:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    return {"error": "Parameter 'year' must be an integer"}
            
            report_type = params.get('report_type')
            limit = params.get('limit', 20)
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = 20
            
            return await get_financial_reports(year=year, report_type=report_type, limit=limit)
        
        elif function == 'get_quarterly_earnings':
            quarters = params.get('quarters', 4)
            try:
                quarters = int(quarters)
            except (ValueError, TypeError):
                quarters = 4
            
            include_tables = params.get('include_tables', 'true').lower() in ('true', '1', 'yes')
            
            return await get_quarterly_earnings(quarters=quarters, include_tables=include_tables)
        
        elif function == 'parse_financial_statement':
            quarter = params.get('quarter')
            year = params.get('year')
            if year is not None:
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    return {"error": "Parameter 'year' must be an integer"}
            
            statement_type = params.get('statement_type', 'all')
            
            return await parse_financial_statement(
                quarter=quarter,
                year=year,
                statement_type=statement_type
            )
        
        else:
            return {"error": f"Unknown function: {function}"}
    
    except Exception as e:
        return {"error": f"Execution error: {str(e)}"}