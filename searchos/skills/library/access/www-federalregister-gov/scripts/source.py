"""
Federal Register API Access Skill

Fetches structured document data from the Federal Register API (federalregister.gov).
Supports document retrieval by ID, search with filters, and agency/topic browsing.

API Documentation: https://www.federalregister.gov/developers/api
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from datetime import datetime

import aiohttp


API_BASE = "https://www.federalregister.gov/api/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Federal Register API requests.
    
    Args:
        params: Dictionary containing:
            - function: The operation to perform
            - Other parameters specific to each function

    
    Returns:
        Dictionary with 'success', 'data'/'error', and optional metadata.
    """
    function = params.get("function", "")
    
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    handlers = {
        "get_document": get_document,
        "search_documents": search_documents,
        "get_agency": get_agency,
        "list_agencies": list_agencies,
        "list_topics": list_topics,
        "get_public_inspection": get_public_inspection,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: {list(handlers.keys())}"
        }
    
    try:
        result = await handler(params)
        return result
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"HTTP error: {str(e)}"}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Request timed out"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def _fetch(
    session: aiohttp.ClientSession,
    url: str,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT
) -> dict | list:
    """Make an API request and return JSON data."""
    headers = {
        "User-Agent": "SearchOS Federal Register Skill/1.0",
        "Accept": "application/json",
    }
    
    async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
        if resp.status == 404:
            raise aiohttp.ClientError(f"Resource not found: {url}")
        if resp.status != 200:
            text = await resp.text()
            raise aiohttp.ClientError(f"API error {resp.status}: {text[:200]}")
        return await resp.json()


def _format_document(doc: dict) -> dict:
    """Format a document record for cleaner output."""
    return {
        "document_number": doc.get("document_number"),
        "title": doc.get("title"),
        "type": doc.get("type"),
        "subtype": doc.get("subtype"),
        "citation": doc.get("citation"),
        "volume": doc.get("volume"),
        "start_page": doc.get("start_page"),
        "end_page": doc.get("end_page"),
        "page_length": doc.get("page_length"),
        "publication_date": doc.get("publication_date"),
        "signing_date": doc.get("signing_date"),
        "effective_on": doc.get("effective_on"),
        "agencies": [
            {
                "name": a.get("name"),
                "slug": a.get("slug"),
                "id": a.get("id")
            }
            for a in doc.get("agencies", [])
        ],
        "executive_order_number": doc.get("executive_order_number"),
        "presidential_document_number": doc.get("presidential_document_number"),
        "proclamation_number": doc.get("proclamation_number"),
        "abstract": doc.get("abstract"),
        "dates": doc.get("dates"),
        "action": doc.get("action"),
        "cfr_references": doc.get("cfr_references", []),
        "topics": doc.get("topics", []),
        "docket_ids": doc.get("docket_ids", []),
        "html_url": doc.get("html_url"),
        "pdf_url": doc.get("pdf_url"),
        "full_text_xml_url": doc.get("full_text_xml_url"),
        "raw_text_url": doc.get("raw_text_url"),
        "page_views": doc.get("page_views", {}).get("count"),
        "significant": doc.get("significant"),
    }


def _format_document_brief(doc: dict) -> dict:
    """Format a brief document summary for search results."""
    return {
        "document_number": doc.get("document_number"),
        "title": doc.get("title"),
        "type": doc.get("type"),
        "subtype": doc.get("subtype"),
        "publication_date": doc.get("publication_date"),
        "agencies": [a.get("name") for a in doc.get("agencies", [])],
        "citation": doc.get("citation"),
        "html_url": doc.get("html_url"),
        "pdf_url": doc.get("pdf_url"),
        "excerpts": doc.get("excerpts"),
    }


async def get_document(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve a single document by document number.
    
    Parameters:
        document_number: The FR document number (e.g., "2025-02096")
        include_full_text: If true, attempt to fetch raw text content (default: false)
    """
    doc_number = params.get("document_number")
    if not doc_number:
        return {"success": False, "error": "Missing required parameter: document_number"}
    
    include_full_text = params.get("include_full_text", False)
    
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE}/documents/{doc_number}.json"
        data = await _fetch(session, url)
        
        result = {
            "success": True,
            "data": _format_document(data),
        }
        
        # Optionally fetch full text
        if include_full_text and data.get("raw_text_url"):
            try:
                headers = {"User-Agent": "SearchOS Federal Register Skill/1.0"}
                async with session.get(data["raw_text_url"], headers=headers, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Check if we got actual text or a blocked response
                        if not text.startswith("<!DOCTYPE html>"):
                            result["data"]["full_text"] = text
            except Exception:
                pass  # Full text is optional
        
        return result


async def search_documents(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search Federal Register documents with filters.
    
    Parameters:
        query: Full-text search query
        document_number: Search by document number (partial match)
        president: President slug (e.g., "donald-trump", "joe-biden")
        agency_slug: Agency slug filter (e.g., "environmental-protection-agency")
        agency_id: Agency ID filter (numeric)
        type: Document type (e.g., "RULE", "PRORULE", "NOTICE", "PRESDOCU")
        topic: Topic slug for filtering
        publication_date_gte: Start date (YYYY-MM-DD)
        publication_date_lte: End date (YYYY-MM-DD)
        publication_year: Year filter (integer)
        cfr_title: CFR title number
        cfr_part: CFR part number
        significant: Filter significant documents ("true" or "false")
        order: Sort order ("newest", "oldest", "relevance")
        per_page: Results per page (1-100, default 20)
        page: Page number for pagination
        fields: Comma-separated list of fields to return (default: all)
    """
    search_params = {}
    
    # Text search
    if params.get("query"):
        search_params["conditions[term]"] = params["query"]
    
    # Document filters
    if params.get("president"):
        search_params["conditions[president]"] = params["president"]
    
    if params.get("agency_slug"):
        search_params["conditions[agencies][]"] = params["agency_slug"]
    elif params.get("agency_id"):
        search_params["conditions[agency_ids][]"] = str(params["agency_id"])
    
    if params.get("type"):
        # Support multiple types as comma-separated
        types = params["type"].split(",") if "," in params["type"] else [params["type"]]
        for i, t in enumerate(types):
            search_params[f"conditions[type][][{i}]"] = t.strip()
    
    if params.get("topic"):
        search_params["conditions[topics][]"] = params["topic"]
    
    # Date filters
    if params.get("publication_date_gte"):
        search_params["conditions[publication_date][gte]"] = params["publication_date_gte"]
    if params.get("publication_date_lte"):
        search_params["conditions[publication_date][lte]"] = params["publication_date_lte"]
    if params.get("publication_year"):
        search_params["conditions[publication_date][year]"] = str(params["publication_year"])
    
    # CFR references
    if params.get("cfr_title"):
        search_params["conditions[cfr][title]"] = str(params["cfr_title"])
    if params.get("cfr_part"):
        search_params["conditions[cfr][part]"] = str(params["cfr_part"])
    
    # Significant filter
    if params.get("significant"):
        search_params["conditions[significant]"] = params["significant"]
    
    # Pagination and ordering
    per_page = min(int(params.get("per_page", DEFAULT_PER_PAGE)), MAX_PER_PAGE)
    search_params["per_page"] = str(per_page)
    
    if params.get("page"):
        search_params["page"] = str(params["page"])
    
    search_params["order"] = params.get("order", "newest")
    
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE}/documents.json"
        data = await _fetch(session, url, search_params)
        
        results = data.get("results", [])
        formatted = [_format_document_brief(r) for r in results]
        
        return {
            "success": True,
            "data": {
                "count": data.get("count", 0),
                "results": formatted,
                "page": data.get("meta", {}).get("page", 1),
                "per_page": per_page,
            },
            "meta": {
                "total_count": data.get("count", 0),
                "returned_count": len(formatted),
            }
        }


async def get_agency(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve details for a specific agency.
    
    Parameters:
        agency_id: Agency ID (numeric)
        agency_slug: Agency slug (e.g., "environmental-protection-agency")
    """
    agency_id = params.get("agency_id")
    agency_slug = params.get("agency_slug")
    
    if not agency_id and not agency_slug:
        return {"success": False, "error": "Missing required parameter: agency_id or agency_slug"}
    
    async with aiohttp.ClientSession() as session:
        if agency_id:
            url = f"{API_BASE}/agencies/{agency_id}.json"
        else:
            # Need to search by slug - get all agencies and filter
            data = await _fetch(session, f"{API_BASE}/agencies.json")
            for agency in data:
                if agency.get("slug") == agency_slug:
                    agency_id = agency.get("id")
                    url = f"{API_BASE}/agencies/{agency_id}.json"
                    break
            else:
                return {"success": False, "error": f"Agency not found: {agency_slug}"}
        
        data = await _fetch(session, url)
        
        return {
            "success": True,
            "data": {
                "id": data.get("id"),
                "name": data.get("name"),
                "short_name": data.get("short_name"),
                "slug": data.get("slug"),
                "description": data.get("description"),
                "url": data.get("url"),
                "agency_url": data.get("agency_url"),
                "parent_id": data.get("parent_id"),
                "child_ids": data.get("child_ids", []),
                "child_slugs": data.get("child_slugs", []),
                "logo": data.get("logo"),
                "recent_articles_url": data.get("recent_articles_url"),
            }
        }


async def list_agencies(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all agencies.
    
    Parameters:
        per_page: Results per page (default: all)
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"{API_BASE}/agencies.json")
        
        agencies = [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "short_name": a.get("short_name"),
                "slug": a.get("slug"),
                "parent_id": a.get("parent_id"),
            }
            for a in data
        ]
        
        return {
            "success": True,
            "data": {
                "count": len(agencies),
                "agencies": agencies,
            }
        }


async def list_topics(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all topics (thesaurus and ad-hoc).
    
    Parameters:
        topic_type: Filter by type ("thesaurus" or "ad_hoc")
    """
    async with aiohttp.ClientSession() as session:
        data = await _fetch(session, f"{API_BASE}/topics.json")
        
        results = data.get("results", {})
        topic_type = params.get("topic_type")
        
        if topic_type:
            topics = results.get(topic_type, [])
        else:
            # Combine both types
            topics = results.get("thesaurus", []) + results.get("ad_hoc", [])
        
        formatted = [
            {
                "name": t.get("name"),
                "slug": t.get("slug"),
                "see": t.get("see", []),
                "see_also": t.get("see_also", []),
            }
            for t in topics
        ]
        
        return {
            "success": True,
            "data": {
                "count": len(formatted),
                "meta": data.get("meta", {}).get("count", {}),
                "topics": formatted,
            }
        }


async def get_public_inspection(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get public inspection documents.
    
    Parameters:
        available_on: Date filter (YYYY-MM-DD)
        per_page: Results per page (1-100, default 20)
        order: Sort order ("newest", "oldest")
    """
    search_params = {}
    
    if params.get("available_on"):
        search_params["conditions[available_on]"] = params["available_on"]
    
    per_page = min(int(params.get("per_page", DEFAULT_PER_PAGE)), MAX_PER_PAGE)
    search_params["per_page"] = str(per_page)
    search_params["order"] = params.get("order", "newest")
    
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE}/public-inspection-documents.json"
        data = await _fetch(session, url, search_params)
        
        results = data.get("results", [])
        formatted = [
            {
                "document_number": r.get("document_number"),
                "title": r.get("title"),
                "type": r.get("type"),
                "publication_date": r.get("publication_date"),
                "agencies": [a.get("name") for a in r.get("agencies", [])],
                "pdf_url": r.get("pdf_url"),
                "html_url": r.get("html_url"),
            }
            for r in results
        ]
        
        return {
            "success": True,
            "data": {
                "count": data.get("count", 0),
                "results": formatted,
            }
        }