"""
SEC EDGAR Access Skill

Provides structured access to SEC EDGAR filings and financial data.
Supports company lookup, filing retrieval, XBRL fact extraction, and table parsing.

SEC requires User-Agent header with contact info for automated access.
"""

import asyncio
import json
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

# SEC requires User-Agent with company/contact info for automated tools
DEFAULT_USER_AGENT = "SearchOS Bot contact@searchos.example.com"
SEC_BASE_URL = "https://www.sec.gov"
EDGAR_DATA_URL = "https://data.sec.gov"

# Rate limiting - SEC requests max 10 requests/second
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60)
_SEMAPHORE = asyncio.Semaphore(5)  # Limit concurrent requests


def _get_headers(user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """Return required headers for SEC requests."""
    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/html, application/xhtml+xml, application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


async def _fetch(url: str, session: aiohttp.ClientSession, headers: dict) -> tuple[int, str]:
    """Fetch URL with rate limiting."""
    async with _SEMAPHORE:
        async with session.get(url, headers=headers, timeout=_REQUEST_TIMEOUT) as resp:
            text = await resp.text()
            return resp.status, text


def _pad_cik(cik: str) -> str:
    """Pad CIK to 10 digits."""
    cik_clean = cik.lstrip("0")
    return cik_clean.zfill(10)


# =============================================================================
# Company Lookup Functions
# =============================================================================

async def get_company_by_ticker(ticker: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    Look up company by ticker symbol.
    
    Returns company CIK, name, and ticker info.
    """
    headers = _get_headers(user_agent)
    ticker = ticker.upper().strip()
    
    async with aiohttp.ClientSession() as session:
        # Fetch ticker mapping
        url = "https://www.sec.gov/files/company_tickers.json"
        status, text = await _fetch(url, session, headers)
        
        if status != 200:
            return {"error": f"Failed to fetch ticker mapping: status {status}", "status": status}
        
        data = json.loads(text)
        
        # Find matching ticker
        for key, entry in data.items():
            if entry.get("ticker", "").upper() == ticker:
                return {
                    "cik": str(entry.get("cik_str", "")),
                    "cik_padded": _pad_cik(str(entry.get("cik_str", ""))),
                    "ticker": entry.get("ticker", ""),
                    "name": entry.get("title", ""),
                    "status": "found"
                }
        
        return {"error": f"Ticker '{ticker}' not found", "status": "not_found"}


async def get_cik_lookup(query: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    Look up CIK by ticker or company name.
    
    Supports partial matching on company name.
    """
    headers = _get_headers(user_agent)
    query = query.strip()
    
    async with aiohttp.ClientSession() as session:
        url = "https://www.sec.gov/files/company_tickers.json"
        status, text = await _fetch(url, session, headers)
        
        if status != 200:
            return {"error": f"Failed to fetch ticker mapping: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        results = []
        query_lower = query.lower()
        
        for key, entry in data.items():
            ticker = entry.get("ticker", "")
            name = entry.get("title", "")
            
            # Exact ticker match
            if ticker.upper() == query.upper():
                return {
                    "matches": [{
                        "cik": str(entry.get("cik_str", "")),
                        "cik_padded": _pad_cik(str(entry.get("cik_str", ""))),
                        "ticker": ticker,
                        "name": name,
                        "match_type": "exact_ticker"
                    }],
                    "status": "found"
                }
            
            # Partial matching
            if query_lower in ticker.lower() or query_lower in name.lower():
                results.append({
                    "cik": str(entry.get("cik_str", "")),
                    "cik_padded": _pad_cik(str(entry.get("cik_str", ""))),
                    "ticker": ticker,
                    "name": name,
                    "match_type": "partial"
                })
        
        if results:
            return {"matches": results[:20], "count": len(results), "status": "found"}
        
        return {"error": f"No matches found for '{query}'", "matches": [], "status": "not_found"}


# =============================================================================
# Company Information Functions
# =============================================================================

async def get_company_info(cik: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    Get company information from SEC submissions API.
    
    Returns name, ticker, SIC, state of incorporation, and filing history.
    """
    headers = _get_headers(user_agent)
    cik_padded = _pad_cik(cik.lstrip("0"))
    
    async with aiohttp.ClientSession() as session:
        url = f"{EDGAR_DATA_URL}/submissions/CIK{cik_padded}.json"
        status, text = await _fetch(url, session, headers)
        
        if status == 404:
            return {"error": f"Company with CIK {cik} not found", "status": "not_found"}
        if status != 200:
            return {"error": f"Failed to fetch company info: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        # Extract recent filings
        recent = data.get("filings", {}).get("recent", {})
        filings = []
        
        if recent:
            forms = recent.get("form", [])
            acc_nums = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            primary_docs = recent.get("primaryDocument", [])
            reports = recent.get("primaryDocDescription", [])
            
            for i in range(min(50, len(forms))):
                acc_num = acc_nums[i] if i < len(acc_nums) else ""
                acc_num_clean = acc_num.replace("-", "")
                filings.append({
                    "form": forms[i] if i < len(forms) else "",
                    "filing_date": filing_dates[i] if i < len(filing_dates) else "",
                    "accession_number": acc_num,
                    "primary_document": primary_docs[i] if i < len(primary_docs) else "",
                    "description": reports[i] if i < len(reports) else "",
                    "filing_url": f"{SEC_BASE_URL}/Archives/edgar/data/{cik}/{acc_num_clean}/{primary_docs[i]}" if i < len(primary_docs) else ""
                })
        
        return {
            "cik": data.get("cik", ""),
            "name": data.get("name", ""),
            "tickers": data.get("tickers", []),
            "exchanges": data.get("exchanges", []),
            "sic": data.get("sic", ""),
            "sic_description": data.get("sicDescription", ""),
            "category": data.get("entityType", ""),
            "fiscal_year_end": data.get("fiscalYearEnd", ""),
            "state": data.get("stateOfIncorporation", ""),
            "state_location": data.get("stateOfIncorporationDescription", ""),
            "ein": data.get("ein", ""),
            "website": data.get("website", ""),
            "phone": data.get("phone", ""),
            "addresses": data.get("addresses", {}),
            "recent_filings": filings,
            "status": "success"
        }


# =============================================================================
# XBRL Financial Data Functions
# =============================================================================

async def get_company_facts(cik: str, user_agent: str = DEFAULT_USER_AGENT) -> dict:
    """
    Get all XBRL facts for a company.
    
    Returns structured financial data from SEC's XBRL API.
    """
    headers = _get_headers(user_agent)
    cik_padded = _pad_cik(cik.lstrip("0"))
    
    async with aiohttp.ClientSession() as session:
        url = f"{EDGAR_DATA_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        status, text = await _fetch(url, session, headers)
        
        if status == 404:
            return {"error": f"No XBRL facts found for CIK {cik}", "status": "not_found"}
        if status != 200:
            return {"error": f"Failed to fetch company facts: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        # Extract available taxonomies and concepts
        facts = data.get("facts", {})
        taxonomies = {}
        concept_count = 0
        
        for taxonomy, concepts in facts.items():
            taxonomies[taxonomy] = list(concepts.keys())[:100]  # First 100 concepts per taxonomy
            concept_count += len(concepts)
        
        return {
            "cik": data.get("cik", ""),
            "name": data.get("name", ""),
            "taxonomies": taxonomies,
            "taxonomy_names": list(facts.keys()),
            "concept_count": concept_count,
            "status": "success"
        }


async def get_financial_data(
    cik: str,
    concepts: list | None = None,
    user_agent: str = DEFAULT_USER_AGENT
) -> dict:
    """
    Get specific financial data for a company.
    
    Extracts key financial metrics from XBRL facts.
    If concepts list is provided, only those are extracted.
    Otherwise, extracts common financial metrics.
    """
    headers = _get_headers(user_agent)
    cik_padded = _pad_cik(cik.lstrip("0"))
    
    # Default key financial concepts
    default_concepts = [
        # Balance Sheet
        "Assets", "AssetsCurrent", "AssetsNoncurrent",
        "Liabilities", "LiabilitiesCurrent", "LiabilitiesNoncurrent",
        "StockholdersEquity",
        "CashAndCashEquivalentsAtCarryingValue",
        "AccountsReceivableNetCurrent",
        "InventoryNet",
        "PropertyPlantAndEquipmentNet",
        # Income Statement
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "CostOfRevenue",
        "GrossProfit",
        "OperatingIncomeLoss",
        "NetIncomeLoss",
        "ResearchAndDevelopmentExpense",
        "SellingGeneralAndAdministrativeExpense",
        # Per Share
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        # Shares
        "CommonStockSharesOutstanding",
        "CommonStockSharesIssued",
        "CommonStockParOrStatedValuePerShare",
    ]
    
    concepts_to_fetch = concepts if concepts else default_concepts
    
    async with aiohttp.ClientSession() as session:
        url = f"{EDGAR_DATA_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        status, text = await _fetch(url, session, headers)
        
        if status == 404:
            return {"error": f"No XBRL facts found for CIK {cik}", "status": "not_found"}
        if status != 200:
            return {"error": f"Failed to fetch company facts: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        us_gaap = data.get("facts", {}).get("us-gaap", {})
        dei = data.get("facts", {}).get("dei", {})
        
        extracted = {}
        
        for concept in concepts_to_fetch:
            if concept in us_gaap:
                fact = us_gaap[concept]
                units = fact.get("units", {})
                
                # Get USD values preferentially
                for unit in ["USD", "shares", "USD/shares", "pure"]:
                    if unit in units:
                        values = units[unit]
                        if values:
                            extracted[concept] = {
                                "unit": unit,
                                "values": values[-10:],  # Last 10 values
                                "label": fact.get("label", ""),
                            }
                            break
        
        # Also extract document info from DEI
        doc_info = {}
        dei_concepts = ["DocumentType", "DocumentFiscalPeriodFocus", "EntityCommonStockSharesOutstanding"]
        for concept in dei_concepts:
            if concept in dei:
                units = dei[concept].get("units", {})
                for unit in ["pure", "shares"]:
                    if unit in units and units[unit]:
                        doc_info[concept] = units[unit][-3:]
        
        return {
            "cik": cik_padded,
            "extracted_facts": extracted,
            "document_info": doc_info,
            "concepts_found": len(extracted),
            "status": "success"
        }


async def get_concept_history(
    cik: str,
    concept: str,
    taxonomy: str = "us-gaap",
    user_agent: str = DEFAULT_USER_AGENT
) -> dict:
    """
    Get the full history for a specific XBRL concept.
    
    Example concepts: Assets, RevenueFromContractWithCustomerExcludingAssessedTax,
    NetIncomeLoss, StockholdersEquity
    """
    headers = _get_headers(user_agent)
    cik_padded = _pad_cik(cik.lstrip("0"))
    
    async with aiohttp.ClientSession() as session:
        url = f"{EDGAR_DATA_URL}/api/xbrl/companyconcept/CIK{cik_padded}/{taxonomy}/{concept}.json"
        status, text = await _fetch(url, session, headers)
        
        if status == 404:
            return {"error": f"Concept '{concept}' not found for CIK {cik}", "status": "not_found"}
        if status != 200:
            return {"error": f"Failed to fetch concept: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        # Organize by unit
        units_data = {}
        for unit, values in data.get("units", {}).items():
            # Sort by end date
            sorted_values = sorted(values, key=lambda x: x.get("end", ""), reverse=True)
            units_data[unit] = sorted_values
        
        return {
            "cik": cik_padded,
            "concept": concept,
            "taxonomy": taxonomy,
            "label": data.get("label", ""),
            "description": data.get("description", "")[:500] if data.get("description") else "",
            "units": units_data,
            "status": "success"
        }


# =============================================================================
# Filing Document Functions
# =============================================================================

async def get_filing_document(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT
) -> dict:
    """
    Fetch and parse a filing document.
    
    Extracts text content, tables, and structured data.
    Handles both standard HTML and iXBRL (inline XBRL) documents.
    """
    headers = _get_headers(user_agent)
    
    if not url.startswith(SEC_BASE_URL) and not url.startswith("https://www.sec.gov"):
        return {"error": "URL must be from sec.gov domain", "status": "invalid_url"}
    
    async with aiohttp.ClientSession() as session:
        status, text = await _fetch(url, session, headers)
        
        if status != 200:
            return {"error": f"Failed to fetch filing: status {status}", "status": status}
        
        # Check if this is a pure XML document (not iXBRL)
        # Pure XML documents like .xml files should be returned as-is
        if url.endswith(".xml") and not text.strip().lower().startswith("<html"):
            return {
                "url": url,
                "title": "",
                "document_type": "xml",
                "content_length": len(text),
                "status": "success",
                "note": "XML document - use specialized parsers for XBRL"
            }
        
        # Parse with BeautifulSoup - use html.parser to handle iXBRL properly
        # iXBRL documents have XML declarations but are HTML documents
        soup = BeautifulSoup(text, "html.parser")
        
        # Basic metadata
        title = soup.title.string if soup.title else ""
        
        # Detect if this is an iXBRL document
        is_ixbrl = bool(soup.find_all(lambda tag: tag.name and tag.name.startswith('ix:'))) or \
                   'xmlns:ix' in text or '<ix:' in text
        
        # Extract document sections
        sections = {}
        text_content = soup.get_text()
        
        section_markers = [
            ("business", ["Item 1.", "Business", "PART I"]),
            ("risk_factors", ["Risk Factors", "Item 1A."]),
            ("selected_financial_data", ["Selected Financial Data", "Item 6."]),
            ("mda", ["Management's Discussion", "Item 7."]),
            ("controls", ["Controls and Procedures", "Item 9A."]),
            ("financial_statements", ["Financial Statements", "Item 8."]),
        ]
        
        for section_name, markers in section_markers:
            for marker in markers:
                if marker in text_content:
                    sections[section_name] = True
                    break
        
        # Extract tables (regular HTML tables)
        tables = soup.find_all("table")
        
        # Extract financial tables with key patterns
        financial_tables = []
        financial_keywords = [
            "consolidated balance sheet",
            "consolidated statement",
            "cash flow",
            "income statement",
            "stockholders equity",
            "comprehensive income",
            "offering price",  # For prospectuses
            "use of proceeds",
        ]
        
        for i, table in enumerate(tables[:150]):  # Check first 150 tables
            table_text = table.get_text(" ", strip=True).lower()
            
            # Skip very small tables (likely layout tables)
            if len(table_text) < 50:
                continue
            
            for keyword in financial_keywords:
                if keyword in table_text:
                    # Extract table structure
                    rows = []
                    for tr in table.find_all("tr")[:40]:  # Limit rows
                        cells = []
                        for cell in tr.find_all(["td", "th"]):
                            cell_text = cell.get_text(strip=True)
                            # Remove excessive whitespace
                            cell_text = " ".join(cell_text.split())
                            if cell_text:
                                cells.append(cell_text)
                        if cells:  # Skip empty rows
                            rows.append(cells)
                    
                    if len(rows) >= 2:
                        financial_tables.append({
                            "index": i,
                            "type": keyword,
                            "rows": rows[:35],  # Limit rows in output
                            "preview": table_text[:500]
                        })
                    break
            
            if len(financial_tables) >= 10:  # Limit financial tables
                break
        
        # Extract iXBRL data if present
        xbrl_facts = []
        if is_ixbrl:
            # Find common iXBRL elements
            for elem in soup.find_all(lambda tag: tag.name and 'ix://' in str(tag.name)):
                fact_value = elem.get_text(strip=True)
                fact_name = elem.get('name', '')
                if fact_value and fact_name:
                    xbrl_facts.append({
                        "name": fact_name,
                        "value": fact_value[:200]
                    })
            
            # Also check for data-* attributes which may contain XBRL data
            for elem in soup.find_all(attrs={"contextref": True}):
                fact_value = elem.get_text(strip=True)
                fact_name = elem.get('name', '')
                context = elem.get('contextref', '')
                if fact_value:
                    xbrl_facts.append({
                        "name": fact_name,
                        "value": fact_value[:200],
                        "context": context
                    })
        
        result = {
            "url": url,
            "title": title,
            "document_type": "ixbrl" if is_ixbrl else "html",
            "content_length": len(text),
            "table_count": len(tables),
            "financial_table_count": len(financial_tables),
            "sections_found": sections,
            "financial_tables": financial_tables,
            "status": "success"
        }
        
        if xbrl_facts:
            result["xbrl_facts_count"] = len(xbrl_facts)
            result["xbrl_facts_sample"] = xbrl_facts[:20]
        
        return result


async def get_filings_by_type(
    cik: str,
    form_type: str = "10-K",
    limit: int = 10,
    user_agent: str = DEFAULT_USER_AGENT
) -> dict:
    """
    Get recent filings of a specific type for a company.
    
    Common form types: 10-K, 10-Q, 8-K, DEF 14A, 4, S-1, 424B4
    """
    headers = _get_headers(user_agent)
    cik_padded = _pad_cik(cik.lstrip("0"))
    
    async with aiohttp.ClientSession() as session:
        url = f"{EDGAR_DATA_URL}/submissions/CIK{cik_padded}.json"
        status, text = await _fetch(url, session, headers)
        
        if status != 200:
            return {"error": f"Failed to fetch submissions: status {status}", "status": status}
        
        import json
        data = json.loads(text)
        
        recent = data.get("filings", {}).get("recent", {})
        cik_num = cik.lstrip("0")
        
        filings = []
        if recent:
            forms = recent.get("form", [])
            acc_nums = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            primary_docs = recent.get("primaryDocument", [])
            reports = recent.get("primaryDocDescription", [])
            
            for i in range(len(forms)):
                if forms[i] == form_type or forms[i].upper() == form_type.upper():
                    acc_num = acc_nums[i]
                    acc_num_clean = acc_num.replace("-", "")
                    filings.append({
                        "form": forms[i],
                        "filing_date": filing_dates[i],
                        "accession_number": acc_num,
                        "primary_document": primary_docs[i],
                        "description": reports[i],
                        "filing_url": f"{SEC_BASE_URL}/Archives/edgar/data/{cik_num}/{acc_num_clean}/{primary_docs[i]}",
                        "directory_url": f"{SEC_BASE_URL}/Archives/edgar/data/{cik_num}/{acc_num_clean}/"
                    })
                    
                    if len(filings) >= limit:
                        break
        
        return {
            "cik": cik_num,
            "form_type": form_type,
            "filings": filings,
            "count": len(filings),
            "status": "success"
        }


def parse_filing_url(url: str) -> dict:
    """
    Parse a SEC filing URL to extract CIK, accession number, and document.
    
    Example: https://www.sec.gov/Archives/edgar/data/2022626/000119312524236714/d843142d424b4.htm
    """
    pattern = r"/edgar/data/(\d+)/(\d+)/(.+)$"
    match = re.search(pattern, url)
    
    if match:
        return {
            "cik": match.group(1),
            "accession_number": match.group(2),
            "document": match.group(3),
            "status": "parsed"
        }
    
    return {"error": "Could not parse filing URL", "status": "invalid_url"}


# =============================================================================
# Main Execute Function
# =============================================================================

async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute SEC EDGAR access functions.
    
    Required params:
        function: One of the defined functions
    
    Functions:
        get_company_by_ticker: Look up company by ticker symbol
            - ticker: str (required)
        
        get_cik_lookup: Search for company by ticker or name
            - query: str (required)
        
        get_company_info: Get company details and recent filings
            - cik: str (required)
        
        get_company_facts: Get available XBRL concepts
            - cik: str (required)
        
        get_financial_data: Get key financial metrics
            - cik: str (required)
            - concepts: list (optional) - specific concepts to fetch
        
        get_concept_history: Get history for a specific concept
            - cik: str (required)
            - concept: str (required)
            - taxonomy: str (optional, default "us-gaap")
        
        get_filing_document: Fetch and parse a filing document
            - url: str (required)
        
        get_filings_by_type: Get filings by form type
            - cik: str (required)
            - form_type: str (optional, default "10-K")
            - limit: int (optional, default 10)
        
        parse_filing_url: Parse a filing URL
            - url: str (required)
    
    Optional params:
        user_agent: str - Custom User-Agent (must include contact info)
    """
    function = params.get("function")
    if not function:
        return {"error": "Missing required parameter: function", "status": "error"}
    
    user_agent = params.get("user_agent", DEFAULT_USER_AGENT)
    
    try:
        if function == "get_company_by_ticker":
            ticker = params.get("ticker")
            if not ticker:
                return {"error": "Missing required parameter: ticker", "status": "error"}
            return await get_company_by_ticker(ticker, user_agent)
        
        elif function == "get_cik_lookup":
            query = params.get("query")
            if not query:
                return {"error": "Missing required parameter: query", "status": "error"}
            return await get_cik_lookup(query, user_agent)
        
        elif function == "get_company_info":
            cik = params.get("cik")
            if not cik:
                return {"error": "Missing required parameter: cik", "status": "error"}
            return await get_company_info(cik, user_agent)
        
        elif function == "get_company_facts":
            cik = params.get("cik")
            if not cik:
                return {"error": "Missing required parameter: cik", "status": "error"}
            return await get_company_facts(cik, user_agent)
        
        elif function == "get_financial_data":
            cik = params.get("cik")
            if not cik:
                return {"error": "Missing required parameter: cik", "status": "error"}
            concepts = params.get("concepts")
            return await get_financial_data(cik, concepts, user_agent)
        
        elif function == "get_concept_history":
            cik = params.get("cik")
            concept = params.get("concept")
            if not cik:
                return {"error": "Missing required parameter: cik", "status": "error"}
            if not concept:
                return {"error": "Missing required parameter: concept", "status": "error"}
            taxonomy = params.get("taxonomy", "us-gaap")
            return await get_concept_history(cik, concept, taxonomy, user_agent)
        
        elif function == "get_filing_document":
            url = params.get("url")
            if not url:
                return {"error": "Missing required parameter: url", "status": "error"}
            return await get_filing_document(url, user_agent)
        
        elif function == "get_filings_by_type":
            cik = params.get("cik")
            if not cik:
                return {"error": "Missing required parameter: cik", "status": "error"}
            form_type = params.get("form_type", "10-K")
            limit = params.get("limit", 10)
            return await get_filings_by_type(cik, form_type, limit, user_agent)
        
        elif function == "parse_filing_url":
            url = params.get("url")
            if not url:
                return {"error": "Missing required parameter: url", "status": "error"}
            return parse_filing_url(url)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_company_by_ticker",
                    "get_cik_lookup",
                    "get_company_info",
                    "get_company_facts",
                    "get_financial_data",
                    "get_concept_history",
                    "get_filing_document",
                    "get_filings_by_type",
                    "parse_filing_url"
                ],
                "status": "error"
            }
    
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "status": "network_error"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "status": "error"}
