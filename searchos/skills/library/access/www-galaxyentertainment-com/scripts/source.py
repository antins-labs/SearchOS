"""
Galaxy Entertainment Group Investor Relations Access Skill

Fetches financial reports and announcements from Galaxy Entertainment Group's 
investor relations section at www.galaxyentertainment.com.

Endpoints:
- Financial Reports: /en/investor/financial-reports (Annual & Interim Reports since 2005)
- Financial Results: /en/investor/financial-results (Quarterly data, meeting results, exchange filings)
"""

import asyncio
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://www.galaxyentertainment.com"

# Page URLs
FINANCIAL_REPORTS_PATH = "/en/investor/financial-reports"
FINANCIAL_RESULTS_PATH = "/en/investor/financial-results"


def parse_date(date_str: str) -> str:
    """Parse various date formats to ISO format YYYY-MM-DD"""
    if not date_str:
        return ""
    
    # Clean up the date string
    date_str = date_str.strip().replace(',', '')
    
    # Common formats to try
    formats = [
        '%b %d %Y',      # "Apr 09 2026"
        '%B %d %Y',      # "April 09 2026"
        '%d %b %Y',      # "09 Apr 2026"
        '%Y-%m-%d',      # "2026-04-09"
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return date_str


def categorize_report(title: str) -> str:
    """Categorize report type based on title"""
    title_lower = title.lower()
    
    if 'annual report' in title_lower:
        return 'Annual Report'
    elif 'interim report' in title_lower:
        return 'Interim Report'
    elif 'sustainability' in title_lower or 'esg' in title_lower:
        return 'Sustainability Report'
    elif 'csr' in title_lower:
        return 'CSR Report'
    else:
        return 'Other'


def categorize_announcement(title: str) -> str:
    """Categorize announcement type based on title"""
    title_lower = title.lower()
    
    if 'monthly return' in title_lower:
        return 'Monthly Return'
    elif 'financial data' in title_lower or 'selected unaudited' in title_lower:
        return 'Financial Data'
    elif 'poll result' in title_lower or 'general meeting' in title_lower:
        return 'Meeting Results'
    elif 'director' in title_lower:
        return 'Directors'
    elif 'next day disclosure' in title_lower:
        return 'Disclosure'
    elif 'exchange announcement' in title_lower or 'stock exchange' in title_lower:
        return 'Exchange Announcement'
    elif 'transaction' in title_lower:
        return 'Transaction'
    elif 'rights issue' in title_lower or 'buy-back' in title_lower:
        return 'Corporate Action'
    else:
        return 'Announcement'


def extract_year_from_title(title: str) -> int | None:
    """Extract year from report title"""
    # Look for 4-digit year
    match = re.search(r'\b(20\d{2})\b', title)
    if match:
        return int(match.group(1))
    return None


async def fetch_page(session: aiohttp.ClientSession, path: str) -> tuple[str | None, str | None]:
    """Fetch page HTML content. Returns (html, error)"""
    url = urljoin(BASE_URL, path)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                return None, f"HTTP {resp.status} for {url}"
            html = await resp.text()
            return html, None
    except asyncio.TimeoutError:
        return None, f"Timeout fetching {url}"
    except Exception as e:
        return None, f"Error fetching {url}: {str(e)}"


def parse_financial_reports(html: str) -> list[dict]:
    """Parse financial reports from HTML content"""
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.pdf' not in href.lower():
            continue
        
        text = a.get_text(strip=True)
        if not text:
            continue
        
        # Match date pattern at start of text
        date_match = re.match(r'^([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})', text)
        if not date_match:
            continue
        
        date_str = date_match.group(1)
        title = text[len(date_str):].strip()
        
        if not title:
            continue
        
        report = {
            'date': parse_date(date_str),
            'title': title,
            'type': categorize_report(title),
            'year': extract_year_from_title(title),
            'url': urljoin(BASE_URL, href),
            'filename': href.split('/')[-1] if '/' in href else href,
        }
        reports.append(report)
    
    # Sort by date descending
    reports.sort(key=lambda x: x['date'], reverse=True)
    return reports


def parse_announcements(html: str) -> list[dict]:
    """Parse announcements from HTML content"""
    soup = BeautifulSoup(html, 'html.parser')
    announcements = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.pdf' not in href.lower():
            continue
        
        text = a.get_text(strip=True)
        if not text:
            continue
        
        # Match date pattern at start of text
        date_match = re.match(r'^([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4})', text)
        if not date_match:
            continue
        
        date_str = date_match.group(1)
        title = text[len(date_str):].strip()
        
        if not title:
            continue
        
        announcement = {
            'date': parse_date(date_str),
            'title': title,
            'type': categorize_announcement(title),
            'url': urljoin(BASE_URL, href),
            'filename': href.split('/')[-1] if '/' in href else href,
        }
        announcements.append(announcement)
    
    # Sort by date descending
    announcements.sort(key=lambda x: x['date'], reverse=True)
    return announcements


async def get_financial_reports(
    report_type: str | None = None,
    year: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Fetch financial reports from Galaxy Entertainment Group.
    
    Args:
        report_type: Filter by type ('Annual Report', 'Interim Report', etc.)
        year: Filter by report year
        limit: Maximum number of results to return
    
    Returns:
        Dict with 'reports' list or 'error' string
    """
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_page(session, FINANCIAL_REPORTS_PATH)
        if error:
            return {'error': error, 'reports': []}
        
        reports = parse_financial_reports(html)
        
        # Apply filters
        filtered = reports
        
        if report_type:
            report_type_lower = report_type.lower()
            filtered = [r for r in filtered if report_type_lower in r['type'].lower()]
        
        if year:
            filtered = [r for r in filtered if r.get('year') == year]
        
        if limit and limit > 0:
            filtered = filtered[:limit]
        
        return {
            'reports': filtered,
            'total': len(reports),
            'filtered_count': len(filtered),
        }


async def get_financial_results(
    doc_type: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Fetch recent financial results and announcements from Galaxy Entertainment Group.
    
    Args:
        doc_type: Filter by document type ('Monthly Return', 'Financial Data', etc.)
        limit: Maximum number of results to return
    
    Returns:
        Dict with 'announcements' list or 'error' string
    """
    async with aiohttp.ClientSession() as session:
        html, error = await fetch_page(session, FINANCIAL_RESULTS_PATH)
        if error:
            return {'error': error, 'announcements': []}
        
        announcements = parse_announcements(html)
        
        # Apply filters
        filtered = announcements
        
        if doc_type:
            doc_type_lower = doc_type.lower()
            filtered = [a for a in filtered if doc_type_lower in a['type'].lower()]
        
        if limit and limit > 0:
            filtered = filtered[:limit]
        
        return {
            'announcements': filtered,
            'total': len(announcements),
            'filtered_count': len(filtered),
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Galaxy Entertainment investor relations skill.
    
    Dispatches based on params['function']:
      - 'financial_reports': Fetch annual and interim reports
      - 'financial_results': Fetch recent announcements and financial data
    
    Returns structured dict with results or error information.
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function', 'valid_functions': ['financial_reports', 'financial_results']}
    
    if function == 'financial_reports':
        report_type = params.get('report_type')
        year = params.get('year')
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {'error': f'Invalid year value: {year}. Must be an integer.', 'reports': []}
        
        limit = params.get('limit')
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return {'error': f'Invalid limit value: {limit}. Must be an integer.', 'reports': []}
        
        return await get_financial_reports(report_type=report_type, year=year, limit=limit)
    
    elif function == 'financial_results':
        doc_type = params.get('doc_type')
        
        limit = params.get('limit')
        if limit is not None:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return {'error': f'Invalid limit value: {limit}. Must be an integer.', 'announcements': []}
        
        return await get_financial_results(doc_type=doc_type, limit=limit)
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'valid_functions': ['financial_reports', 'financial_results']
        }