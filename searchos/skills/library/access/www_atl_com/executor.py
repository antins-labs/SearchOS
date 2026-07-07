"""
ATL (Hartsfield-Jackson Atlanta International Airport) Operating Statistics Access Skill

Provides access to monthly airport traffic reports including passenger counts,
aircraft operations, cargo data, and carrier-specific breakdowns.
"""

import asyncio
import re
from typing import Any, Optional
import io
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader


BASE_URL = "https://www.atl.com"
STATISTICS_URL = f"{BASE_URL}/business-information/statistics/"


async def fetch_page_with_browser(url: str) -> str:
    """Fetch page content using browser automation."""
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            content = await page.content()
            await browser.close()
            
            return content
    except Exception as e:
        return ""


async def download_pdf_with_browser(pdf_url: str) -> Optional[bytes]:
    """Download a PDF using browser automation to bypass restrictions."""
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Navigate to statistics page first to set cookies
            await page.goto(STATISTICS_URL, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Download the PDF
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f'window.open("{pdf_url}", "_blank")')
            
            download = await download_info.value
            path = await download.path()
            
            with open(path, 'rb') as f:
                content = f.read()
            
            await browser.close()
            return content
            
    except Exception as e:
        return None


def parse_statistics_page(html: str) -> dict:
    """Parse the statistics page to extract available reports."""
    soup = BeautifulSoup(html, 'html.parser')
    
    reports = {}
    year_pattern = re.compile(r'^(20\d{2})$')
    month_pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)$')
    month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'June': 6,
                'July': 7, 'Aug': 8, 'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
    
    # Find all tables
    tables = soup.find_all('table')
    
    for table in tables:
        # Look for year headers (h3 inside the table)
        h3 = table.find('h3')
        if not h3:
            continue
        
        year_match = year_pattern.match(h3.get_text(strip=True))
        if not year_match:
            continue
        
        year = int(year_match.group(1))
        if year not in reports:
            reports[year] = {}
        
        # Extract month links
        for link in table.find_all('a'):
            month_text = link.get_text(strip=True)
            month_match = month_pattern.match(month_text)
            if month_match:
                month_name = month_match.group(1)
                month_num = month_map[month_name]
                
                pdf_url = link.get('href', '')
                if pdf_url:
                    reports[year][month_num] = {
                        'month_name': month_name,
                        'month': month_num,
                        'year': year,
                        'pdf_url': pdf_url
                    }
    
    return reports


def parse_passengers_table(text: str) -> list[dict]:
    """Extract passenger data from PDF text."""
    passengers = []
    
    # Look for passenger data
    # The format shows: Category Current Previous
    patterns = [
        (r'Domestic\s+On\s+([\d,]+)\s+([\d,]+)', 'Domestic On'),
        (r'Domestic\s+Off\s+([\d,]+)\s+([\d,]+)', 'Domestic Off'),
        (r'International\s+On\s+([\d,]+)\s+([\d,]+)', 'International On'),
        (r'International\s+Off\s+([\d,]+)\s+([\d,]+)', 'International Off'),
    ]
    
    for pattern, category in patterns:
        match = re.search(pattern, text)
        if match:
            passengers.append({
                'category': category,
                'current': int(match.group(1).replace(',', '')),
                'previous': int(match.group(2).replace(',', ''))
            })
    
    # Total passengers
    total_match = re.search(r'TOTAL\s+PASSENGERS\s+([\d,]+)\s+([\d,]+)', text)
    if total_match:
        passengers.append({
            'category': 'Total Passengers',
            'current': int(total_match.group(1).replace(',', '')),
            'previous': int(total_match.group(2).replace(',', ''))
        })
    
    return passengers


def parse_aircraft_operations(text: str) -> list[dict]:
    """Extract aircraft operations data from PDF text."""
    operations = []
    
    # Look for aircraft operations by type
    # Two formats possible: operations table with Domestic/International split or combined
    patterns = [
        (r'Air Carrier\s+([\d,]+)\s+([\d,]+)', 'Air Carrier'),
        (r'Air\s*Taxi\s+([\d,]+)\s+([\d,]+)', 'Air Taxi'),
        (r'General\s*Aviation\s+([\d,]+)\s+([\d,]+)', 'General Aviation'),
        (r'Military\s+([\d,]+)\s+([\d,]+)', 'Military'),
    ]
    
    for pattern, category in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            operations.append({
                'category': category,
                'current': int(match.group(1).replace(',', '')),
                'previous': int(match.group(2).replace(',', ''))
            })
    
    # Total operations
    total_match = re.search(r'TOTAL\s+AIRCRAFT\s+OPERATIONS\s+[^\d]*([\d,]+)\s+([\d,]+)', text, re.IGNORECASE)
    if total_match:
        operations.append({
            'category': 'Total Operations',
            'current': int(total_match.group(1).replace(',', '')),
            'previous': int(total_match.group(2).replace(',', ''))
        })
    
    return operations


def parse_cargo_data(text: str) -> dict:
    """Extract cargo (freight and mail) data from PDF text."""
    cargo = {}
    
    # Freight & Express
    freight_match = re.search(r'Total\s+Freight\s*&\s*Express\s+([\d,]+)\s+([\d,]+)', text, re.IGNORECASE)
    if freight_match:
        cargo['freight'] = {
            'current_metric_tons': int(freight_match.group(1).replace(',', '')),
            'previous_metric_tons': int(freight_match.group(2).replace(',', ''))
        }
    
    # Mail
    mail_match = re.search(r'Total\s+Mail\s+([\d,]+)', text)
    if mail_match:
        cargo['mail'] = {
            'current_metric_tons': int(mail_match.group(1).replace(',', ''))
        }
    
    # Also try to find grand total cargo
    cargo_total_match = re.search(r'GRAND\s+TOTAL\s+CARGO[^0-9]*([\d,]+)', text, re.IGNORECASE)
    if cargo_total_match:
        cargo['total'] = {
            'current_metric_tons': int(cargo_total_match.group(1).replace(',', ''))
        }
    
    return cargo


def parse_change_percentages(text: str) -> dict:
    """Extract year-over-year change percentages from PDF text."""
    changes = {}
    
    # Look for change percentages near key metrics
    passenger_change = re.search(r'TOTAL\s+PASSENGERS[^%]*?(-?[\d.]+)%', text)
    if passenger_change:
        changes['passengers_pct_change'] = float(passenger_change.group(1))
    
    ops_change = re.search(r'TOTAL\s+AIRCRAFT\s+OPERATIONS[^%]*?(-?[\d.]+)%', text)
    if ops_change:
        changes['operations_pct_change'] = float(ops_change.group(1))
    
    return changes


def extract_pdf_data(pdf_content: bytes) -> dict:
    """Extract structured data from PDF content."""
    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        
        # Extract all text from all pages
        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text())
        
        full_text = '\n'.join(pages_text)
        
        # Extract title info (Month Year)
        title_match = re.search(r'(\w+)\s+(\d{4})\s+Monthly\s+Airport\s+Traffic\s+Report', full_text)
        month_year = {
            'month': title_match.group(1) if title_match else None,
            'year': int(title_match.group(2)) if title_match else None
        }
        
        # Parse structured data
        passengers = parse_passengers_table(full_text)
        operations = parse_aircraft_operations(full_text)
        cargo = parse_cargo_data(full_text)
        changes = parse_change_percentages(full_text)
        
        return {
            'title': f"Monthly Airport Traffic Report - {month_year.get('month', 'Unknown')} {month_year.get('year', 'Unknown')}",
            'month': month_year.get('month'),
            'year': month_year.get('year'),
            'passengers': passengers,
            'aircraft_operations': operations,
            'cargo': cargo,
            'year_over_year_changes': changes if changes else None,
            'page_count': len(reader.pages),
            'pdf_size_bytes': len(pdf_content),
            'raw_text_sample': full_text[:2000]  # Sample for debugging
        }
    except Exception as e:
        return {
            'error': f'Failed to parse PDF: {str(e)}',
            'page_count': 0,
            'pdf_size_bytes': len(pdf_content)
        }


async def find_latest_report(reports: dict) -> Optional[dict]:
    """Find the most recent available report."""
    # Sort years descending
    sorted_years = sorted(reports.keys(), reverse=True)
    
    for year in sorted_years:
        # Sort months descending
        sorted_months = sorted(reports[year].keys(), reverse=True)
        
        for month in sorted_months:
            return reports[year][month]
    
    return None


async def list_statistics(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """List available monthly operating statistics reports."""
    # Use browser to fetch the page
    html = await fetch_page_with_browser(STATISTICS_URL)
    
    if not html:
        return {
            'error': 'Failed to fetch statistics page',
            'url': STATISTICS_URL
        }
    
    reports = parse_statistics_page(html)
    
    # Filter by year if specified
    year = params.get('year')
    if year:
        if year in reports:
            reports = {year: reports[year]}
        else:
            return {
                'error': f'No reports found for year {year}',
                'available_years': list(reports.keys())
            }
    
    # Format response
    result = {
        'page_url': STATISTICS_URL,
        'available_years': sorted(reports.keys(), reverse=True),
        'total_reports': sum(len(months) for months in reports.values()),
        'reports': {}
    }
    
    for yr in sorted(reports.keys(), reverse=True):
        result['reports'][yr] = {
            'months': [
                {
                    'month': reports[yr][m]['month'],
                    'month_name': reports[yr][m]['month_name'],
                    'pdf_url': reports[yr][m]['pdf_url']
                }
                for m in sorted(reports[yr].keys())
            ]
        }
    
    return result


async def get_pdf_data(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Download and extract data from a statistics PDF."""
    pdf_url = params.get('pdf_url')
    year = params.get('year')
    month = params.get('month')
    
    # If we have year/month but no URL, get the URL first
    if not pdf_url and year and month:
        html = await fetch_page_with_browser(STATISTICS_URL)
        if not html:
            return {'error': 'Failed to fetch statistics page'}
        
        reports = parse_statistics_page(html)
        
        if year not in reports:
            return {'error': f'No reports found for year {year}'}
        if month not in reports[year]:
            return {'error': f'No report found for {year}/{month}'}
        
        pdf_url = reports[year][month]['pdf_url']
    
    if not pdf_url:
        return {'error': 'pdf_url or both year and month are required'}
    
    # Download PDF using browser automation
    pdf_content = await download_pdf_with_browser(pdf_url)
    
    if not pdf_content:
        return {
            'error': 'Failed to download PDF',
            'pdf_url': pdf_url
        }
    
    # Extract data
    data = extract_pdf_data(pdf_content)
    data['pdf_url'] = pdf_url
    
    return data


async def get_latest_report(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Get the most recent monthly report with extracted data."""
    html = await fetch_page_with_browser(STATISTICS_URL)
    
    if not html:
        return {'error': 'Failed to fetch statistics page'}
    
    reports = parse_statistics_page(html)
    latest = await find_latest_report(reports)
    
    if not latest:
        return {'error': 'No reports found on the statistics page'}
    
    # Download and extract the PDF
    pdf_content = await download_pdf_with_browser(latest['pdf_url'])
    
    if not pdf_content:
        return {
            'error': 'Failed to download latest PDF',
            'pdf_url': latest['pdf_url'],
            'month': latest['month_name'],
            'year': latest['year']
        }
    
    data = extract_pdf_data(pdf_content)
    data['pdf_url'] = latest['pdf_url']
    
    return data


async def get_page_content(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Get the raw content summary of the statistics page."""
    html = await fetch_page_with_browser(STATISTICS_URL)
    
    if not html:
        return {
            'error': 'Failed to fetch page',
            'url': STATISTICS_URL
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract main content
    title = soup.find('title')
    h1 = soup.find('h1')
    
    return {
        'url': STATISTICS_URL,
        'title': title.get_text(strip=True) if title else None,
        'h1': h1.get_text(strip=True) if h1 else None,
        'reports': parse_statistics_page(html),
        'html_length': len(html)
    }


async def execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Main entry point for the ATL statistics skill."""
    function = params.get('function', 'list_statistics')
    
    handlers = {
        'list_statistics': list_statistics,
        'get_pdf_data': get_pdf_data,
        'get_latest_report': get_latest_report,
        'get_page_content': get_page_content,
    }
    
    if function not in handlers:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': list(handlers.keys())
        }
    
    return await handlers[function](params, ctx)