"""
UN ICTR/MICT Case Documents Access Skill

Provides structured access to the United Nations International Criminal Tribunal for Rwanda (ICTR)
and Mechanism for International Criminal Tribunals (MICT) case documents database.

API Endpoints:
- /api/Summary/ByCaseDetail - Get case details (case name, description)
- /api/Summary/ByCaseRelatedDocs - Get all documents for a case
- /api/Summary/ByCaseDocsByLang - Get documents filtered by language

Document Types:
- Jdg: Judgement/Sentence
- Dec: Decision
- Ord: Order
- TRA: Transcript
- IND: Indictment
- MOT: Motion
- APP: Application
- And many others...
"""

import asyncio
import json
from typing import Any
import aiohttp


BASE_URL = "https://ucr.irmct.org"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Document type descriptions
DOC_TYPE_DESCRIPTIONS = {
    "Jdg": "Judgement/Sentence",
    "Dec": "Decision",
    "Ord": "Order",
    "TRA": "Transcript",
    "IND": "Indictment",
    "REV": "Revised Indictment",
    "ADL": "Amended Indictment",
    "MOT": "Motion",
    "APP": "Application",
    "WIT": "Witness List",
    "SUB": "Submission",
    "REQ": "Request",
    "BRP": "Pre-Trial Brief",
    "BRI": "Brief",
    "BRF": "Final Brief",
    "WSS": "Warrant Search",
    "WAA": "Warrant Arrest",
    "MED": "Medical Report",
    "MIS": "Miscellaneous",
    "TAP": "Court Recording/Video",
    "DOP": "Disposition",
    "SEN": "Sentence",
    "SCH": "Schedule",
}

# Source descriptions
DOC_SOURCE_DESCRIPTIONS = {
    "APC": "Appeals Chamber",
    "JUD": "Trial Chamber",
    "TCI": "Trial Chamber I",
    "T1A": "Trial Chamber I/A",
    "TII": "Trial Chamber II",
    "T2A": "Trial Chamber II/A",
    "T2B": "Trial Chamber II/B",
    "T33": "Trial Chamber III",
    "T75": "Trial Chamber",
    "TSA": "Trial Chamber",
    "TCB": "Trial Chamber B",
    "CHA": "Chamber",
    "PRE": "President",
    "REG": "Registry",
}

# Language codes
LANGUAGE_CODES = {
    "ENG": "English",
    "FRA": "French",
    "KIN": "Kinyarwanda",
    "HBS": "Bosnian/Croatian/Serbian",
    "OTH": "Other",
}


async def fetch_api(session: aiohttp.ClientSession, endpoint: str, params: dict, timeout: int = 30) -> dict:
    """Fetch data from the API endpoint."""
    url = f"{BASE_URL}{endpoint}"
    try:
        async with session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}", "status_code": resp.status}
            
            data = await resp.json()
            if "data" in data:
                parsed = json.loads(data["data"])
                return {"data": parsed, "success": True}
            return {"data": data, "success": True}
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "success": False}
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {str(e)}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def get_case_detail(case_number: str) -> dict:
    """
    Get case details (case ID, number, description/defendant name).
    
    Args:
        case_number: Case number (e.g., "ICTR-97-23", "MICT-13-38")
    
    Returns:
        dict with case details or error
    """
    async with aiohttp.ClientSession() as session:
        result = await fetch_api(session, "/api/Summary/ByCaseDetail", {"CaseNumber": case_number})
        
        if not result.get("success"):
            return result
        
        data = result.get("data", [])
        if not data:
            return {"error": f"Case '{case_number}' not found", "success": False}
        
        case = data[0]
        return {
            "success": True,
            "case": {
                "case_id": case.get("CaseId"),
                "case_number": case.get("CaseNumber"),
                "description": case.get("CaseDescription"),
            }
        }


async def get_case_documents(case_number: str, language: str = None, doc_type: str = None) -> dict:
    """
    Get documents for a case, optionally filtered by language.
    
    Args:
        case_number: Case number (e.g., "ICTR-97-23", "MICT-13-38")
        language: Optional language filter (ENG, FRA, KIN, HBS, OTH)
        doc_type: Optional document type filter (Jdg, Dec, Ord, TRA, etc.)
    
    Returns:
        dict with list of documents or error
    """
    async with aiohttp.ClientSession() as session:
        # Use language-filtered endpoint if language specified
        if language:
            params = {"CaseNumber": case_number, "Lang": language.upper()}
            result = await fetch_api(session, "/api/Summary/ByCaseDocsByLang", params, timeout=60)
        else:
            params = {"CaseNumber": case_number}
            result = await fetch_api(session, "/api/Summary/ByCaseRelatedDocs", params, timeout=60)
        
        if not result.get("success"):
            return result
        
        documents = result.get("data", [])
        
        # Filter by document type if specified
        if doc_type:
            doc_type_upper = doc_type.upper()
            documents = [d for d in documents if d.get("DocumentType", "").upper() == doc_type_upper]
        
        # Format documents
        formatted_docs = []
        for doc in documents:
            formatted_docs.append({
                "document_id": doc.get("DocumentId"),
                "title": doc.get("DocumentTitle"),
                "case_number": doc.get("CaseNumber"),
                "case_description": doc.get("CaseDescription"),
                "document_type": doc.get("DocumentType"),
                "document_type_desc": doc.get("DocTypeDesc") or DOC_TYPE_DESCRIPTIONS.get(doc.get("DocumentType")),
                "document_source": doc.get("DocumentSource"),
                "document_source_desc": doc.get("DocSourceDesc") or DOC_SOURCE_DESCRIPTIONS.get(doc.get("DocumentSource")),
                "filing_date": doc.get("DocFilingDate"),
                "signature_date": doc.get("DocSignatureDate"),
                "language": doc.get("Lang"),
                "language_full": doc.get("DocumentLanguage") or LANGUAGE_CODES.get(doc.get("Lang")),
                "document_path": doc.get("DocumentPath"),
            })
        
        return {
            "success": True,
            "case_number": case_number,
            "language_filter": language,
            "doc_type_filter": doc_type,
            "total_documents": len(formatted_docs),
            "documents": formatted_docs,
        }


async def get_documents_by_category(case_number: str) -> dict:
    """
    Get documents grouped by category (document type).
    
    Args:
        case_number: Case number (e.g., "ICTR-97-23")
    
    Returns:
        dict with documents grouped by category
    """
    async with aiohttp.ClientSession() as session:
        result = await fetch_api(session, "/api/Summary/ByCaseRelatedDocs", {"CaseNumber": case_number}, timeout=60)
        
        if not result.get("success"):
            return result
        
        documents = result.get("data", [])
        
        # Group by document type
        categories = {}
        for doc in documents:
            doc_type = doc.get("DocumentType", "Unknown")
            if doc_type not in categories:
                categories[doc_type] = {
                    "type_code": doc_type,
                    "type_description": doc.get("DocTypeDesc") or DOC_TYPE_DESCRIPTIONS.get(doc_type, "Unknown"),
                    "count": 0,
                    "documents": [],
                }
            
            categories[doc_type]["count"] += 1
            categories[doc_type]["documents"].append({
                "document_id": doc.get("DocumentId"),
                "title": doc.get("DocumentTitle"),
                "source": doc.get("DocSourceDesc"),
                "filing_date": doc.get("DocFilingDate"),
                "language": doc.get("Lang"),
                "document_path": doc.get("DocumentPath"),
            })
        
        # Sort categories by count
        sorted_categories = dict(sorted(categories.items(), key=lambda x: x[1]["count"], reverse=True))
        
        return {
            "success": True,
            "case_number": case_number,
            "total_documents": len(documents),
            "categories": sorted_categories,
        }


async def search_documents(case_number: str, query: str = None, date_from: str = None, date_to: str = None) -> dict:
    """
    Search documents with optional filters.
    
    Args:
        case_number: Case number
        query: Optional text search in document title
        date_from: Optional start date filter (DD/MM/YYYY format)
        date_to: Optional end date filter (DD/MM/YYYY format)
    
    Returns:
        dict with matching documents
    """
    async with aiohttp.ClientSession() as session:
        result = await fetch_api(session, "/api/Summary/ByCaseRelatedDocs", {"CaseNumber": case_number}, timeout=60)
        
        if not result.get("success"):
            return result
        
        documents = result.get("data", [])
        filtered = []
        
        for doc in documents:
            # Text search in title
            if query:
                title = doc.get("DocumentTitle", "").lower()
                if query.lower() not in title:
                    continue
            
            # Date filtering (dates are in DD/MM/YYYY format)
            doc_date = doc.get("DocFilingDate", "")
            if date_from and doc_date:
                # Simple string comparison works for DD/MM/YYYY format
                if doc_date < date_from:
                    continue
            
            if date_to and doc_date:
                if doc_date > date_to:
                    continue
            
            filtered.append({
                "document_id": doc.get("DocumentId"),
                "title": doc.get("DocumentTitle"),
                "document_type": doc.get("DocumentType"),
                "document_type_desc": doc.get("DocTypeDesc"),
                "source": doc.get("DocSourceDesc"),
                "filing_date": doc.get("DocFilingDate"),
                "language": doc.get("Lang"),
                "document_path": doc.get("DocumentPath"),
            })
        
        return {
            "success": True,
            "case_number": case_number,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "total_results": len(filtered),
            "documents": filtered,
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on params["function"]:
    - get_case_detail: Get case information
    - get_documents: Get all documents for a case
    - get_documents_by_category: Get documents grouped by type
    - search_documents: Search documents with filters
    """
    function = params.get("function", "")
    
    if function == "get_case_detail":
        case_number = params.get("case_number")
        if not case_number:
            return {"error": "Missing required parameter: case_number", "success": False}
        return await get_case_detail(case_number)
    
    elif function == "get_documents":
        case_number = params.get("case_number")
        if not case_number:
            return {"error": "Missing required parameter: case_number", "success": False}
        language = params.get("language")
        doc_type = params.get("doc_type")
        return await get_case_documents(case_number, language, doc_type)
    
    elif function == "get_documents_by_category":
        case_number = params.get("case_number")
        if not case_number:
            return {"error": "Missing required parameter: case_number", "success": False}
        return await get_documents_by_category(case_number)
    
    elif function == "search_documents":
        case_number = params.get("case_number")
        if not case_number:
            return {"error": "Missing required parameter: case_number", "success": False}
        query = params.get("query")
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        return await search_documents(case_number, query, date_from, date_to)
    
    else:
        return {
            "error": f"Unknown function: {function}. Available functions: get_case_detail, get_documents, get_documents_by_category, search_documents",
            "success": False
        }