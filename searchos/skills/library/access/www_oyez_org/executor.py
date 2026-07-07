"""
Oyez.org Supreme Court Case Database Access Skill

This skill provides access to the Oyez.org API for retrieving Supreme Court case data
including case details, oral arguments, opinions, and timeline information.

API Notes:
- Base URL: https://api.oyez.org
- Cases endpoint: /cases/{term}/{docket}?labels=true
- Term listing: /cases/{term}?labels=true&page={n}
- The API returns all cases when querying any term (the term in URL is ignored)
- Cases are sorted by citation order; recent terms appear at high page numbers (~280+)
"""

import asyncio
import re
from datetime import datetime
from typing import Any
import aiohttp


# Base API URL
API_BASE = "https://api.oyez.org"

# Default HTTP headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.oyez.org/",
}


def parse_timestamp(ts: int) -> str:
    """Convert Unix timestamp to ISO date string."""
    if ts is None or ts == 0:
        return None
    try:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None


def extract_text_from_html(html: str) -> str:
    """Strip HTML tags and clean up text."""
    if not html:
        return None
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    return text if text else None


def format_case_summary(case_data: dict) -> dict:
    """Format a case into a clean summary structure."""
    # Parse timeline events
    timeline = []
    for event in case_data.get("timeline") or []:
        dates = event.get("dates") or []
        timeline.append({
            "event": event.get("event"),
            "date": parse_timestamp(dates[0]) if dates else None,
        })
    
    # Parse citation - handle missing page numbers
    citation = case_data.get("citation") or {}
    citation_str = None
    if citation:
        vol = citation.get("volume", "")
        page = citation.get("page")
        year = citation.get("year", "")
        if vol:
            if page:
                citation_str = f"{vol} U.S. {page} ({year})" if year else f"{vol} U.S. {page}"
            else:
                # Pending cases may not have page numbers yet
                citation_str = f"{vol} U.S. ___ ({year})" if year else f"{vol} U.S. ___"
    
    # Build summary
    summary = {
        "id": case_data.get("ID"),
        "name": case_data.get("name"),
        "docket_number": case_data.get("docket_number"),
        "term": case_data.get("term"),
        "citation": citation_str,
        "first_party": case_data.get("first_party"),
        "second_party": case_data.get("second_party"),
        "first_party_label": case_data.get("first_party_label"),
        "second_party_label": case_data.get("second_party_label"),
        "timeline": timeline,
        "manner_of_jurisdiction": extract_text_from_html(case_data.get("manner_of_jurisdiction")),
        "lower_court": (case_data.get("lower_court") or {}).get("name"),
        "justia_url": case_data.get("justia_url"),
        "api_url": case_data.get("href"),
    }
    
    return {k: v for k, v in summary.items() if v is not None}


def format_court_info(court_data) -> dict:
    """Format court information from heard_by or decided_by field."""
    if not court_data:
        return None
    
    # heard_by is sometimes a list
    if isinstance(court_data, list):
        if len(court_data) == 0:
            return None
        court_data = court_data[0]
    
    if not isinstance(court_data, dict):
        return None
    
    members = []
    for m in court_data.get("members") or []:
        if m.get("name"):
            members.append(m.get("name"))
    
    return {
        "name": court_data.get("name"),
        "justices": members,
    }


def format_case_detail(case_data: dict) -> dict:
    """Format a case into a detailed structure with all available information."""
    # Start with summary
    detail = format_case_summary(case_data)
    
    # Add HTML-stripped content fields
    facts = case_data.get("facts_of_the_case")
    if facts:
        detail["facts_of_the_case"] = extract_text_from_html(facts)
    
    question = case_data.get("question")
    if question:
        detail["question"] = extract_text_from_html(question)
    
    conclusion = case_data.get("conclusion")
    if conclusion:
        detail["conclusion"] = extract_text_from_html(conclusion)
    
    # Add description if available
    description = case_data.get("description")
    if description:
        detail["description"] = extract_text_from_html(description)
    
    # Parse advocates
    advocates = []
    for adv in case_data.get("advocates") or []:
        advocate_data = adv.get("advocate") or {}
        advocates.append({
            "name": advocate_data.get("name"),
            "role": adv.get("advocate_description"),
        })
    if advocates:
        detail["advocates"] = advocates
    
    # Parse written opinions
    opinions = []
    for op in case_data.get("written_opinion") or []:
        opinions.append({
            "type": (op.get("type") or {}).get("label"),
            "author": op.get("judge_full_name"),
            "title": op.get("title"),
            "justia_url": op.get("justia_opinion_url"),
        })
    if opinions:
        detail["written_opinions"] = opinions
    
    # Parse oral argument audio
    audio = []
    for arg in case_data.get("oral_argument_audio") or []:
        audio.append({
            "title": arg.get("title"),
            "unavailable": arg.get("unavailable"),
            "api_url": arg.get("href"),
        })
    if audio:
        detail["oral_argument_audio"] = audio
    
    # Parse decisions with voting breakdown
    decisions = []
    for dec in case_data.get("decisions") or []:
        votes = []
        for vote in dec.get("votes") or []:
            member = vote.get("member") or {}
            votes.append({
                "justice": member.get("name"),
                "vote": vote.get("vote"),
            })
        decisions.append({
            "description": dec.get("description"),
            "votes": votes,
        })
    if decisions:
        detail["decisions"] = decisions
    
    # Parse court information from decided_by
    decided_by = case_data.get("decided_by")
    if decided_by:
        court = format_court_info(decided_by)
        if court:
            detail["court"] = court
    
    # Parse additional docket numbers
    additional_dockets = case_data.get("additional_docket_numbers")
    if additional_dockets:
        detail["additional_docket_numbers"] = additional_dockets
    
    return detail


async def fetch_json(
    session: aiohttp.ClientSession, 
    url: str, 
    headers: dict = None
) -> tuple[int, Any]:
    """Fetch JSON from URL and return (status_code, data)."""
    try:
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        async with session.get(url, headers=req_headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return resp.status, await resp.json()
            else:
                text = await resp.text()
                return resp.status, {"error": f"HTTP {resp.status}", "body": text[:500]}
    except asyncio.TimeoutError:
        return 0, {"error": "Request timeout"}
    except aiohttp.ClientError as e:
        return 0, {"error": str(e)}


async def get_case(session: aiohttp.ClientSession, term: str, docket: str) -> dict:
    """Get a specific case by term and docket number."""
    url = f"{API_BASE}/cases/{term}/{docket}?labels=true"
    status, data = await fetch_json(session, url)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", "Unknown error"),
            "status_code": status,
        }
    
    # Handle case where API returns a list (happens when docket not found)
    if isinstance(data, list):
        # The API sometimes returns a paginated list instead of a 404
        # Try to find a matching docket in the list
        for item in data:
            if isinstance(item, dict) and item.get("docket_number") == docket:
                data = item
                break
        else:
            # No matching docket found - this is likely an invalid docket
            return {
                "success": False,
                "error": f"Case not found: docket {docket} not found in term {term}",
            }
    
    return {
        "success": True,
        "case": format_case_detail(data),
    }


async def search_cases(
    session: aiohttp.ClientSession, 
    query: str,
    max_terms: int = 5
) -> dict:
    """
    Search for cases by name or docket number.
    
    Since the API doesn't have a search endpoint and returns cases in reverse
    chronological order by citation, we search:
    - Recent pages (280-290) for current term cases
    - Beginning pages (0-20) for landmark older cases
    """
    query_lower = query.lower()
    results = []
    seen_dockets = set()
    
    # Search recent and older cases in parallel
    pages_to_check = [283, 284, 285, 286, 287, 0, 1, 2, 3, 4]
    
    tasks = []
    for page in pages_to_check:
        url = f"{API_BASE}/cases/2024?labels=true&page={page}"
        tasks.append(fetch_json(session, url))
    
    responses = await asyncio.gather(*tasks)
    
    for status, data in responses:
        if status != 200 or not isinstance(data, list):
            continue
        
        for case in data:
            name = (case.get("name") or "").lower()
            docket = (case.get("docket_number") or "")
            
            if query_lower in name or query_lower in docket.lower():
                if docket not in seen_dockets:
                    seen_dockets.add(docket)
                    results.append(format_case_summary(case))
    
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results[:50],
    }


async def get_cases_by_term(
    session: aiohttp.ClientSession, 
    term: str, 
    page: int = 0
) -> dict:
    """
    Get cases for a specific term.
    
    Note: API returns all cases regardless of term in URL.
    This returns the raw page data; use search_cases to find specific cases.
    """
    url = f"{API_BASE}/cases/{term}?labels=true&page={page}"
    status, data = await fetch_json(session, url)
    
    if status != 200:
        return {
            "success": False,
            "error": data.get("error", "Unknown error"),
            "status_code": status,
        }
    
    if not isinstance(data, list):
        return {
            "success": False,
            "error": "Unexpected response format",
        }
    
    cases = [format_case_summary(c) for c in data]
    
    # Filter by term if specified
    term_str = str(term)
    filtered_cases = [c for c in cases if c.get("term") == term_str]
    
    return {
        "success": True,
        "term": term,
        "page": page,
        "count": len(cases),
        "cases": cases,
        "note": f"Showing {len(filtered_cases)} cases matching term {term} out of {len(cases)} total on this page. Use search_cases for term-specific searches."
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Oyez case database access.
    
    Functions:
        - get_case: Get a specific Supreme Court case by term and docket number
        - get_cases_by_term: Get a page of cases (note: API returns all terms mixed)
        - search_cases: Search for cases by name or docket number
    
    Parameters for get_case:
        - term: Court term year (e.g., "2024", "2023")
        - docket: Docket number (e.g., "23-1239", "22-45")
    
    Parameters for get_cases_by_term:
        - term: Court term year (for reference; API returns all terms)
        - page: Page number (default 0, 30 cases per page)
    
    Parameters for search_cases:
        - query: Search string (case name or docket number)
        - max_terms: Ignored (kept for backward compatibility)
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "available_functions": ["get_case", "get_cases_by_term", "search_cases"],
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "get_case":
            term = params.get("term")
            docket = params.get("docket")
            
            if not term:
                return {
                    "success": False,
                    "error": "Missing required parameter: term",
                }
            if not docket:
                return {
                    "success": False,
                    "error": "Missing required parameter: docket",
                }
            
            return await get_case(session, term, docket)
        
        elif function == "get_cases_by_term":
            term = params.get("term")
            
            if not term:
                return {
                    "success": False,
                    "error": "Missing required parameter: term",
                }
            
            page = params.get("page", 0)
            return await get_cases_by_term(session, term, page)
        
        elif function == "search_cases":
            query = params.get("query")
            
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: query",
                }
            
            max_terms = params.get("max_terms", 5)
            return await search_cases(session, query, max_terms)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": ["get_case", "get_cases_by_term", "search_cases"],
            }