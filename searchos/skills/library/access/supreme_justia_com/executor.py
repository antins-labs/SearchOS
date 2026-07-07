"""
Justia Supreme Court Opinions Access Skill

Fetches U.S. Supreme Court opinions from Justia's database at supreme.justia.com.
The site is protected by Cloudflare, so we use curl_cffi with Safari impersonation.

Key endpoints:
- Year index: /cases/federal/us/year/{year}.html
- Case page: /cases/federal/us/{volume}/{docket}/
- Volume index: /cases/federal/us/{volume}/
"""

from typing import Any, Optional
import re
from bs4 import BeautifulSoup

# Use curl_cffi for Cloudflare bypass
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

BASE_URL = "https://supreme.justia.com"
IMPERSONATE = "safari15_5"
TIMEOUT = 30


def fetch_url(url: str) -> dict:
    """Fetch a URL using curl_cffi with Safari impersonation."""
    if not HAS_CURL_CFFI:
        return {"error": "curl_cffi is required for this skill", "url": url}
    
    try:
        resp = curl_requests.get(url, impersonate=IMPERSONATE, timeout=TIMEOUT)
        
        if resp.status_code == 403:
            return {"error": "Access denied (Cloudflare challenge)", "status_code": 403, "url": url}
        
        if resp.status_code == 404:
            return {"error": "Page not found", "status_code": 404, "url": url}
        
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "status_code": resp.status_code, "url": url}
        
        if "Just a moment" in resp.text:
            return {"error": "Cloudflare challenge not bypassed", "url": url}
        
        return {"success": True, "html": resp.text, "url": url}
    
    except Exception as e:
        return {"error": str(e), "url": url}


def parse_year_page(html: str) -> dict:
    """Parse a year index page and extract case listings."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the results container
    results = soup.find('div', class_='results')
    if not results:
        return {"error": "No results container found", "cases": []}
    
    # Find all search-result divs
    case_divs = results.find_all('div', class_='search-result')
    
    cases = []
    for div in case_divs:
        # Get case name link
        name_link = div.find('a', class_='case-name')
        if not name_link:
            continue
        
        title = name_link.get_text(strip=True)
        href = name_link.get('href', '')
        
        # Parse volume and docket from href
        match = re.search(r'/cases/federal/us/(\d+)/([\d\-]+)/?$', href)
        if not match:
            continue
        
        volume, docket = match.groups()
        
        # Get text content for metadata
        text = div.get_text()
        
        # Extract docket number
        docket_match = re.search(r'Docket Number:\s*([\d\-]+)', text)
        docket_num = docket_match.group(1) if docket_match else docket
        
        # Extract date
        date_match = re.search(r'Date:\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', text)
        date = date_match.group(1) if date_match else None
        
        # Get summary
        summary_p = div.find('p', class_='result-summary')
        summary = summary_p.get_text(strip=True) if summary_p else None
        
        # Check for Justia Summary badge
        has_summary = div.find('span', attrs={'data-badge-text': 'Justia Summary'}) is not None
        has_annotation = div.find('span', attrs={'data-badge-text': 'Justia Annotation'}) is not None
        
        cases.append({
            'volume': volume,
            'docket': docket_num,
            'title': title,
            'date': date,
            'has_justia_summary': has_summary,
            'has_justia_annotation': has_annotation,
            'summary': summary,
            'url': f'{BASE_URL}{href}' if href.startswith('/') else href
        })
    
    # Get page title
    h1 = soup.find('h1')
    page_title = h1.get_text(strip=True) if h1 else None
    
    return {
        'cases': cases,
        'total': len(cases),
        'page_title': page_title
    }


def parse_case_page(html: str, volume: str, docket: str) -> dict:
    """Parse a case detail page and extract structured information."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'volume': volume,
        'docket': docket,
        'url': f'{BASE_URL}/cases/federal/us/{volume}/{docket}/'
    }
    
    # Get case title (h1)
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
        result['title'] = title
        
        # Parse citation from title
        citation_match = re.search(r'(\d+)\s+U\.S\.\s+(___|\d+)\s+\((\d{4})\)', title)
        if citation_match:
            result['citation'] = {
                'volume': citation_match.group(1),
                'page': citation_match.group(2),
                'year': citation_match.group(3),
                'full': citation_match.group(0)
            }
    
    # Get case details (docket, dates)
    case_details = soup.find('div', class_='case-details')
    if case_details:
        details_text = case_details.get_text()
        
        # Extract docket
        docket_match = re.search(r'Docket\s*No\.?\s*([\d\-]+)', details_text, re.I)
        if docket_match:
            result['docket_number'] = docket_match.group(1)
        
        # Extract granted date
        granted_match = re.search(r'Granted:\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', details_text)
        if granted_match:
            result['granted_date'] = granted_match.group(1)
        
        # Extract argued date
        argued_match = re.search(r'Argued:\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', details_text)
        if argued_match:
            result['argued_date'] = argued_match.group(1)
        
        # Extract decided date
        decided_match = re.search(r'Decided:\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', details_text)
        if decided_match:
            result['decided_date'] = decided_match.group(1)
    
    # Find opinion content
    opinions_div = soup.find('div', id='opinions')
    if opinions_div:
        # Find hidden-content divs (tabs)
        opinion_tabs = opinions_div.find_all('div', id=re.compile(r'tab-opinion-'))
        
        opinions = []
        for tab in opinion_tabs:
            opinion_text = tab.get_text(strip=True)
            
            # Determine opinion type
            opinion_type = "unknown"
            if re.search(r'per\s+curiam', opinion_text, re.I):
                opinion_type = "per_curiam"
            elif re.search(r'dissent', opinion_text, re.I):
                opinion_type = "dissent"
            elif re.search(r'concur', opinion_text, re.I):
                opinion_type = "concurrence"
            elif re.search(r'(?:opinion\s+of\s+the\s+court|delivered\s+the\s+opinion)', opinion_text, re.I):
                opinion_type = "majority"
            
            # Get snippet (first significant text)
            # Skip the NOTICE header
            notice_idx = opinion_text.find('NOTICE:')
            if notice_idx >= 0:
                start_idx = opinion_text.find('Per Curiam', notice_idx)
                if start_idx < 0:
                    start_idx = notice_idx + 50
            else:
                start_idx = 0
            
            snippet = opinion_text[start_idx:start_idx + 1500].strip()
            
            opinions.append({
                'type': opinion_type,
                'tab_id': tab.get('id'),
                'length': len(opinion_text),
                'snippet': snippet
            })
        
        result['opinions'] = opinions
        result['opinion_count'] = len(opinions)
    
    # Get PDF link(s)
    pdf_links = []
    for link in soup.find_all('a', href=re.compile(r'supremecourt\.gov.*\.pdf')):
        href = link.get('href')
        text = link.get_text(strip=True)
        # Only add unique PDFs (from supremecourt.gov opinions)
        if 'opinions' in href and href not in [p['url'] for p in pdf_links]:
            pdf_links.append({
                'url': href,
                'label': text or 'Opinion PDF'
            })
    
    if pdf_links:
        result['pdf_urls'] = pdf_links
        result['official_pdf'] = pdf_links[0]['url'] if pdf_links else None
    
    # Get related materials
    materials_div = soup.find('div', id='materials')
    if materials_div:
        materials = []
        for link in materials_div.find_all('a', href=re.compile(r'\.pdf', re.I))[:20]:
            href = link.get('href')
            text = link.get_text(strip=True)
            if href and text:
                materials.append({
                    'url': href,
                    'label': text[:100]
                })
        if materials:
            result['materials'] = materials
    
    return result


def parse_volume_page(html: str, volume: str) -> dict:
    """Parse a volume index page and extract case listings."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Same structure as year page
    results = soup.find('div', class_='results')
    if not results:
        return {"error": "No results container found", "cases": []}
    
    case_divs = results.find_all('div', class_='search-result')
    
    cases = []
    for div in case_divs:
        name_link = div.find('a', class_='case-name')
        if not name_link:
            continue
        
        title = name_link.get_text(strip=True)
        href = name_link.get('href', '')
        
        # Parse docket from href
        match = re.search(r'/cases/federal/us/\d+/([\d\-]+)/?$', href)
        if not match:
            continue
        
        docket = match.group(1)
        text = div.get_text()
        
        # Extract date
        date_match = re.search(r'Date:\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', text)
        date = date_match.group(1) if date_match else None
        
        cases.append({
            'volume': volume,
            'docket': docket,
            'title': title,
            'date': date,
            'url': f'{BASE_URL}{href}' if href.startswith('/') else href
        })
    
    h1 = soup.find('h1')
    page_title = h1.get_text(strip=True) if h1 else f'Volume {volume}'
    
    return {
        'volume': volume,
        'cases': cases,
        'total': len(cases),
        'page_title': page_title
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a Justia Supreme Court query.
    
    Available functions:
    - get_year_cases: Get cases from a specific year
    - get_case: Get details of a specific case
    - get_volume_cases: Get cases from a specific volume
    - search_cases: Search for cases (limited to year browsing)
    """
    function = params.get("function", "")
    
    if function == "get_year_cases":
        year = params.get("year")
        if not year:
            return {"error": "Year parameter is required"}
        
        # Validate year
        try:
            year_int = int(year)
            if year_int < 1790 or year_int > 2030:
                return {"error": f"Invalid year: {year}. Must be between 1790 and 2030"}
        except ValueError:
            return {"error": f"Invalid year format: {year}"}
        
        url = f"{BASE_URL}/cases/federal/us/year/{year}.html"
        result = fetch_url(url)
        
        if not result.get("success"):
            return result
        
        parsed = parse_year_page(result["html"])
        return {
            "success": True,
            "year": year,
            "url": url,
            **parsed
        }
    
    elif function == "get_case":
        volume = params.get("volume")
        docket = params.get("docket")
        
        if not volume or not docket:
            return {"error": "Both volume and docket parameters are required"}
        
        # Clean inputs
        volume = str(volume).strip()
        docket = str(docket).strip()
        
        url = f"{BASE_URL}/cases/federal/us/{volume}/{docket}/"
        result = fetch_url(url)
        
        if not result.get("success"):
            return result
        
        parsed = parse_case_page(result["html"], volume, docket)
        return {
            "success": True,
            **parsed
        }
    
    elif function == "get_volume_cases":
        volume = params.get("volume")
        if not volume:
            return {"error": "Volume parameter is required"}
        
        volume = str(volume).strip()
        url = f"{BASE_URL}/cases/federal/us/{volume}/"
        result = fetch_url(url)
        
        if not result.get("success"):
            return result
        
        parsed = parse_volume_page(result["html"], volume)
        return {
            "success": True,
            "url": url,
            **parsed
        }
    
    elif function == "search_cases":
        query = params.get("query", "").strip()
        year = params.get("year")
        
        # Justia doesn't have a simple API for search, so we'll use year filtering
        if year:
            return execute({"function": "get_year_cases", "year": year}, ctx)
        
        return {
            "error": "Search requires either a year parameter or query. Use get_year_cases for year-based browsing.",
            "hint": "Try get_year_cases with a year parameter (e.g., 2024, 2025)"
        }
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_year_cases", "get_case", "get_volume_cases", "search_cases"]
        }