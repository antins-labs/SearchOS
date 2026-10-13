"""
DICJ (Macau Gaming Inspection and Coordination Bureau) Data Access Skill

Provides access to Macau gaming statistics including:
- Monthly gross gaming revenue
- Quarterly statistics by game type
- Concessionaire financial reports

Data sources are XML files served directly from www.dicj.gov.mo
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Any, Optional
from datetime import datetime
import re


# Base URLs
BASE_URL = "https://www.dicj.gov.mo"

# Data endpoints
MONTHLY_STATS_PATH = "/web/{lang}/information/DadosEstat_mensal/{year}/report_{lang}.xml"
QUARTERLY_STATS_PATH = "/web/{lang}/information/DadosEstat/{year}/report_{lang}.xml"
FINANCIAL_REPORTS_PATH = "/web/{lang}/information/relcontas/{concessionaire}/index.html"
FINANCIAL_REPORT_PAGE = "/web/{lang}/information/relcontas/{concessionaire}/RC{year}.html"

# Concessionaire codes
CONCESSIONAIRES = {
    "SJM": {"cn": "澳娛綜合度假股份有限公司", "en": "SJM Resorts, S.A.", "pt": "SJM Resorts, S.A."},
    "Wynn": {"cn": "永利渡假村（澳門）股份有限公司", "en": "Wynn Resorts (Macau), S.A.", "pt": "Wynn Resorts (Macau), S.A."},
    "Galaxy": {"cn": "銀河娛樂場股份有限公司", "en": "Galaxy Casino, S.A.", "pt": "Galaxy Casino, S.A."},
    "Venetian": {"cn": "威尼斯人澳門股份有限公司", "en": "Venetian Macau, S.A.", "pt": "Venetian Macau, S.A."},
    "MGM": {"cn": "美高梅金殿超濠股份有限公司", "en": "MGM Grand Paradise, S.A.", "pt": "MGM Grand Paradise, S.A."},
    "PBL": {"cn": "新濠博亞（澳門）股份有限公司", "en": "Melco Resorts (Macau) Limited", "pt": "Melco Resorts (Macau) Limited"},
    "WingHing": {"cn": "榮興彩票有限公司", "en": "Wing Hing Lottery Company, Limited", "pt": "Wing Hing Lottery Company, Limited"},
    "SLOT": {"cn": "澳門彩票有限公司", "en": "Macau Lottery Services, Limited", "pt": "Macau Lottery Services, Limited"},
}

# Language codes
LANGUAGES = ["cn", "en", "pt"]

# Month names in different languages
MONTH_NAMES = {
    "cn": ["一月份", "二月份", "三月份", "四月份", "五月份", "六月份", 
           "七月份", "八月份", "九月份", "十月份", "十一月份", "十二月份"],
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "pt": ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
           "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
}


def parse_xml_statistics(xml_content: str) -> dict:
    """Parse XML statistics data into structured dict"""
    soup = BeautifulSoup(xml_content, 'xml')
    result = {
        "reports": [],
        "last_update": None,
        "next_update": None
    }
    
    stats = soup.find('STATISTICS')
    if stats:
        result["last_update"] = stats.get('lastupdate', '')
        result["next_update"] = stats.get('nextupdate', '')
    
    for report in soup.find_all('REPORT'):
        report_data = {
            "id": report.get('id', ''),
            "title": "",
            "remarks": "",
            "headers": [],
            "subheaders": [],
            "records": []
        }
        
        # Title
        title = report.find('TITLE')
        if title:
            report_data["title"] = title.text.strip()
        
        # Remarks
        remarks = report.find('REMARKS')
        if remarks:
            report_data["remarks"] = remarks.text.strip()
        
        # Headers
        header = report.find('HEADER')
        if header:
            for col in header.find_all('COLUMN', recursive=False):
                report_data["headers"].append({
                    "text": col.text.strip(),
                    "rowspan": col.get('rowspan', '1'),
                    "colspan": col.get('colspan', '1')
                })
            
            sub = header.find('SUB')
            if sub:
                for col in sub.find_all('COLUMN'):
                    report_data["subheaders"].append(col.text.strip())
        
        # Data records
        data = report.find('DATA')
        if data:
            for record in data.find_all('RECORD'):
                record_data = []
                for item in record.find_all('DATA'):
                    record_data.append(item.text.strip())
                report_data["records"].append(record_data)
        
        result["reports"].append(report_data)
    
    return result


def parse_monthly_revenue(data: dict, lang: str = "en") -> list[dict]:
    """Parse monthly revenue report into structured records"""
    records = []
    
    for report in data.get("reports", []):
        title = report.get("title", "")
        
        # Check if this is a monthly revenue report
        for rec in report.get("records", []):
            if len(rec) >= 7:
                record = {
                    "month": rec[0],
                    "current_year_value": rec[1] if len(rec) > 1 else None,
                    "previous_year_value": rec[2] if len(rec) > 2 else None,
                    "change_rate": rec[3] if len(rec) > 3 else None,
                    "current_year_cumulative": rec[4] if len(rec) > 4 else None,
                    "previous_year_cumulative": rec[5] if len(rec) > 5 else None,
                    "cumulative_change_rate": rec[6] if len(rec) > 6 else None,
                }
                records.append(record)
    
    return records


def parse_quarterly_statistics(data: dict) -> list[dict]:
    """Parse quarterly statistics into structured records"""
    all_records = []
    
    for report in data.get("reports", []):
        report_records = {
            "report_id": report.get("id", ""),
            "title": report.get("title", ""),
            "remarks": report.get("remarks", ""),
            "headers": report.get("headers", []),
            "subheaders": report.get("subheaders", []),
            "data": []
        }
        
        for rec in report.get("records", []):
            if rec and any(cell for cell in rec if cell):
                report_records["data"].append(rec)
        
        all_records.append(report_records)
    
    return all_records


def extract_tables_from_html(html_content: str) -> list[dict]:
    """Extract financial data tables from HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = []
    
    for table_idx, table in enumerate(soup.find_all('table')):
        table_data = {
            "index": table_idx,
            "rows": []
        }
        
        for row in table.find_all('tr'):
            cells = []
            for cell in row.find_all(['th', 'td']):
                text = cell.get_text(strip=True)
                cells.append(text)
            if cells:
                table_data["rows"].append(cells)
        
        if table_data["rows"]:
            tables.append(table_data)
    
    return tables


def extract_financial_text(html_content: str) -> str:
    """Extract relevant financial text from HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'head', 'header', 'footer', 'nav']):
        element.decompose()
    
    # Get text
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    return '\n'.join(lines)


async def fetch_url(url: str, client: httpx.AsyncClient) -> dict:
    """Fetch URL and return status/content"""
    try:
        resp = await client.get(url)
        return {
            "status": resp.status_code,
            "content": resp.text if resp.status_code == 200 else None,
            "error": None
        }
    except Exception as e:
        return {
            "status": 0,
            "content": None,
            "error": str(e)
        }


async def get_monthly_revenue(
    year: int,
    lang: str = "en",
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Get monthly gross gaming revenue statistics
    
    Args:
        year: Year to fetch (e.g., 2024)
        lang: Language code ('cn', 'en', 'pt')
        client: Optional httpx client
    
    Returns:
        dict with revenue data by month
    """
    url = BASE_URL + MONTHLY_STATS_PATH.format(lang=lang, year=year)
    
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    try:
        result = await fetch_url(url, client)
        
        if result["status"] != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data: HTTP {result['status']}",
                "url": url
            }
        
        parsed = parse_xml_statistics(result["content"])
        records = parse_monthly_revenue(parsed, lang)
        
        return {
            "success": True,
            "year": year,
            "language": lang,
            "title": parsed["reports"][0]["title"] if parsed["reports"] else None,
            "remarks": parsed["reports"][0].get("remarks", "") if parsed["reports"] else None,
            "monthly_data": records,
            "url": url
        }
    finally:
        if own_client:
            await client.aclose()


async def get_quarterly_statistics(
    year: int,
    lang: str = "en",
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Get quarterly gaming statistics (multiple report types)
    
    Report types include:
    1. Gross revenue by gaming category
    2. Betting volumes for pari-mutuel and lotteries
    3. Gross revenue by game type (baccarat, slots, etc.)
    4. Number of gaming tables and machines
    5. Visitor statistics
    
    Args:
        year: Year to fetch (e.g., 2024)
        lang: Language code ('cn', 'en', 'pt')
        client: Optional httpx client
    
    Returns:
        dict with quarterly statistics data
    """
    url = BASE_URL + QUARTERLY_STATS_PATH.format(lang=lang, year=year)
    
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    try:
        result = await fetch_url(url, client)
        
        if result["status"] != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data: HTTP {result['status']}",
                "url": url
            }
        
        parsed = parse_xml_statistics(result["content"])
        reports = parse_quarterly_statistics(parsed)
        
        return {
            "success": True,
            "year": year,
            "language": lang,
            "report_count": len(reports),
            "reports": reports,
            "url": url
        }
    finally:
        if own_client:
            await client.aclose()


async def get_concessionaire_reports_list(
    concessionaire: str,
    lang: str = "cn",
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Get list of available financial reports for a concessionaire
    
    Args:
        concessionaire: Concessionaire code (SJM, Wynn, Galaxy, Venetian, MGM, PBL, WingHing, SLOT)
        lang: Language code
        client: Optional httpx client
    
    Returns:
        dict with list of available reports by year
    """
    if concessionaire not in CONCESSIONAIRES:
        return {
            "success": False,
            "error": f"Invalid concessionaire code. Valid codes: {list(CONCESSIONAIRES.keys())}"
        }
    
    url = BASE_URL + FINANCIAL_REPORTS_PATH.format(lang=lang, concessionaire=concessionaire)
    
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    try:
        result = await fetch_url(url, client)
        
        if result["status"] != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data: HTTP {result['status']}",
                "url": url
            }
        
        # Parse the HTML to extract report links
        soup = BeautifulSoup(result["content"], 'html.parser')
        reports = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Look for RC*.html pattern
            if 'RC' in href and '.html' in href:
                # Extract year from href
                match = re.search(r'RC(\d{4})', href)
                if match:
                    year = match.group(1)
                    reports.append({
                        "year": int(year),
                        "text": text,
                        "url": BASE_URL + f"/web/{lang}/information/relcontas/{concessionaire}/RC{year}.html"
                    })
        
        # Sort by year descending
        reports.sort(key=lambda x: x["year"], reverse=True)
        
        return {
            "success": True,
            "concessionaire": concessionaire,
            "concessionaire_name": CONCESSIONAIRES[concessionaire].get(lang, CONCESSIONAIRES[concessionaire]["en"]),
            "language": lang,
            "reports": reports,
            "url": url
        }
    finally:
        if own_client:
            await client.aclose()


async def get_concessionaire_financial_report(
    concessionaire: str,
    year: int,
    lang: str = "cn",
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Get financial report content for a specific concessionaire and year
    
    Args:
        concessionaire: Concessionaire code (SJM, Wynn, Galaxy, Venetian, MGM, PBL, WingHing, SLOT)
        year: Report year (e.g., 2024)
        lang: Language code
        client: Optional httpx client
    
    Returns:
        dict with report content including tables and text
    """
    if concessionaire not in CONCESSIONAIRES:
        return {
            "success": False,
            "error": f"Invalid concessionaire code. Valid codes: {list(CONCESSIONAIRES.keys())}"
        }
    
    url = BASE_URL + FINANCIAL_REPORT_PAGE.format(
        lang=lang, 
        concessionaire=concessionaire, 
        year=year
    )
    
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    try:
        result = await fetch_url(url, client)
        
        if result["status"] != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data: HTTP {result['status']}",
                "url": url
            }
        
        # Extract tables and text from HTML
        tables = extract_tables_from_html(result["content"])
        text = extract_financial_text(result["content"])
        
        return {
            "success": True,
            "concessionaire": concessionaire,
            "concessionaire_name": CONCESSIONAIRES[concessionaire].get(lang, CONCESSIONAIRES[concessionaire]["en"]),
            "year": year,
            "language": lang,
            "table_count": len(tables),
            "tables": tables,
            "text_content": text[:10000] if len(text) > 10000 else text,  # Limit text length
            "url": url
        }
    finally:
        if own_client:
            await client.aclose()


async def list_all_concessionaires(lang: str = "en") -> dict:
    """
    List all gaming concessionaires with their codes
    
    Args:
        lang: Language for names ('cn', 'en', 'pt')
    
    Returns:
        dict with concessionaire codes and names
    """
    return {
        "success": True,
        "language": lang,
        "concessionaires": [
            {
                "code": code,
                "name": names.get(lang, names["en"])
            }
            for code, names in CONCESSIONAIRES.items()
        ]
    }


async def get_available_years(
    data_type: str = "monthly",
    lang: str = "en",
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Check which years have available data
    
    Args:
        data_type: 'monthly' or 'quarterly'
        lang: Language code
        client: Optional httpx client
    
    Returns:
        dict with list of available years
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, verify=False)
    
    try:
        current_year = datetime.now().year
        years_to_check = list(range(current_year, 2004, -1))  # Check from current year to 2005
        available_years = []
        
        for year in years_to_check:
            if data_type == "monthly":
                url = BASE_URL + MONTHLY_STATS_PATH.format(lang=lang, year=year)
            else:
                url = BASE_URL + QUARTERLY_STATS_PATH.format(lang=lang, year=year)
            
            result = await fetch_url(url, client)
            if result["status"] == 200:
                available_years.append(year)
        
        return {
            "success": True,
            "data_type": data_type,
            "language": lang,
            "available_years": available_years,
            "year_range": f"{min(available_years)}-{max(available_years)}" if available_years else None
        }
    finally:
        if own_client:
            await client.aclose()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for DICJ data access skill
    
    Required params:
        function: One of:
          - 'get_monthly_revenue': Get monthly gaming revenue data
          - 'get_quarterly_statistics': Get quarterly statistics data
          - 'get_concessionaire_reports': List reports for a concessionaire
          - 'get_financial_report': Get specific financial report
          - 'list_concessionaires': List all concessionaires
          - 'check_years': Check available data years
    
    Function-specific params:
        get_monthly_revenue:
            - year: int (required) - Year to fetch
            - lang: str (optional, default='en') - Language code
        
        get_quarterly_statistics:
            - year: int (required) - Year to fetch
            - lang: str (optional, default='en') - Language code
        
        get_concessionaire_reports:
            - concessionaire: str (required) - Concessionaire code
            - lang: str (optional, default='cn') - Language code
        
        get_financial_report:
            - concessionaire: str (required) - Concessionaire code
            - year: int (required) - Report year
            - lang: str (optional, default='cn') - Language code
        
        list_concessionaires:
            - lang: str (optional, default='en') - Language for names
        
        check_years:
            - data_type: str (optional, default='monthly') - 'monthly' or 'quarterly'
            - lang: str (optional, default='en') - Language code
    
    Returns:
        dict with 'success' bool and either data or error message
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter 'function'. Valid functions: get_monthly_revenue, get_quarterly_statistics, get_concessionaire_reports, get_financial_report, list_concessionaires, check_years"
        }
    
    try:
        if function == "get_monthly_revenue":
            year = params.get("year")
            if not year:
                return {"success": False, "error": "Missing required parameter 'year'"}
            
            lang = params.get("lang", "en")
            if lang not in LANGUAGES:
                return {"success": False, "error": f"Invalid language. Valid: {LANGUAGES}"}
            
            return await get_monthly_revenue(int(year), lang)
        
        elif function == "get_quarterly_statistics":
            year = params.get("year")
            if not year:
                return {"success": False, "error": "Missing required parameter 'year'"}
            
            lang = params.get("lang", "en")
            if lang not in LANGUAGES:
                return {"success": False, "error": f"Invalid language. Valid: {LANGUAGES}"}
            
            return await get_quarterly_statistics(int(year), lang)
        
        elif function == "get_concessionaire_reports":
            concessionaire = params.get("concessionaire")
            if not concessionaire:
                return {"success": False, "error": f"Missing required parameter 'concessionaire'. Valid codes: {list(CONCESSIONAIRES.keys())}"}
            
            concessionaire = concessionaire.upper()
            lang = params.get("lang", "cn")
            
            return await get_concessionaire_reports_list(concessionaire, lang)
        
        elif function == "get_financial_report":
            concessionaire = params.get("concessionaire")
            year = params.get("year")
            
            if not concessionaire:
                return {"success": False, "error": f"Missing required parameter 'concessionaire'. Valid codes: {list(CONCESSIONAIRES.keys())}"}
            if not year:
                return {"success": False, "error": "Missing required parameter 'year'"}
            
            concessionaire = concessionaire.upper()
            lang = params.get("lang", "cn")
            
            return await get_concessionaire_financial_report(concessionaire, int(year), lang)
        
        elif function == "list_concessionaires":
            lang = params.get("lang", "en")
            return await list_all_concessionaires(lang)
        
        elif function == "check_years":
            data_type = params.get("data_type", "monthly")
            if data_type not in ["monthly", "quarterly"]:
                return {"success": False, "error": "Invalid data_type. Must be 'monthly' or 'quarterly'"}
            
            lang = params.get("lang", "en")
            return await get_available_years(data_type, lang)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Valid functions: get_monthly_revenue, get_quarterly_statistics, get_concessionaire_reports, get_financial_report, list_concessionaires, check_years"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {function}: {str(e)}"
        }