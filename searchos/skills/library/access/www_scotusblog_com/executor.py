"""
SCOTUSblog Access Skill

Fetches Supreme Court case data from SCOTUSblog's Sanity CMS API.

The Sanity CMS is publicly accessible at:
https://pito4za5.api.sanity.io/v1/data/query/production

Key document types:
- case: Supreme Court cases
- scotusTerm: Court terms (ot2024, ot2025, etc.)
- docketNumber: Docket numbers
- author: Opinion authors (justices)
"""

import httpx
from typing import Any, Optional
from datetime import datetime

# Sanity CMS configuration
SANITY_PROJECT_ID = "pito4za5"
SANITY_DATASET = "production"
SANITY_API_URL = f"https://{SANITY_PROJECT_ID}.api.sanity.io/v1/data/query/{SANITY_DATASET}"

# Headers for requests
HEADERS = {
    "User-Agent": "SearchOS/1.0 (SCOTUSblog Skill)",
    "Accept": "application/json",
}


def extract_text_from_blocks(blocks: list) -> str:
    """Extract plain text from Sanity PortableText blocks."""
    if not blocks:
        return ""
    
    texts = []
    for block in blocks:
        if block.get("_type") == "block" and block.get("children"):
            block_text = "".join(
                child.get("text", "")
                for child in block["children"]
                if child.get("_type") == "span"
            )
            if block_text:
                texts.append(block_text)
    
    return " ".join(texts)


def format_case(case: dict, proceedings: list = None) -> dict:
    """Format a case document for output."""
    result = {
        "slug": case.get("slug", ""),
        "title": case.get("title", ""),
        "docket_number": case.get("docket_number"),
        "status": case.get("status"),
        "term": case.get("term"),
        "date_argued": case.get("dateArgued"),
        "date_decided": case.get("dateDecided"),
        "vote": case.get("vote"),
        "opinion_author": case.get("opinion_author"),
        "result": case.get("result"),
        "result_details": case.get("resultDetails"),
        "sitting": case.get("sitting"),
        "supreme_court_url": case.get("supremeCourtPageUrl"),
        "opinion_url": case.get("opinionLink"),
        "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
    }
    
    # Extract text from blocks
    if case.get("holding"):
        result["holding"] = extract_text_from_blocks(case["holding"])
    if case.get("judgment"):
        result["judgment"] = extract_text_from_blocks(case["judgment"])
    if case.get("issueArea"):
        result["issue_area"] = extract_text_from_blocks(case["issueArea"])
    
    # Format proceedings
    if proceedings is not None:
        result["proceedings"] = [
            {
                "date": p.get("date"),
                "description": p.get("description"),
                "color": p.get("color"),
                "url": p.get("url"),
            }
            for p in proceedings
            if p.get("date")
        ]
    
    return result


async def run_groq_query(query: str) -> dict:
    """Execute a GROQ query against the Sanity API."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        try:
            response = await client.get(SANITY_API_URL, params={"query": query})
            response.raise_for_status()
            data = response.json()
            return {"success": True, "result": data.get("result")}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP error: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"success": False, "error": f"Request error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def list_terms(params: dict) -> dict:
    """List all Supreme Court terms with case counts."""
    query = '*[_type == "scotusTerm"]{title, "slug": slug.current, startDate, endDate, "case_count": count(*[_type == "case" && scotusTerm._ref == ^._id])}|order(startDate desc)'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    terms = []
    for term in result["result"]:
        terms.append({
            "title": term.get("title"),
            "slug": term.get("slug"),
            "start_date": term.get("startDate"),
            "end_date": term.get("endDate"),
            "case_count": term.get("case_count", 0),
            "url": f"https://www.scotusblog.com/cases/term/{term.get('slug', '')}/",
        })
    
    return {"success": True, "terms": terms}


async def get_term_cases(params: dict) -> dict:
    """Get all cases for a specific term."""
    term_slug = params.get("term")
    if not term_slug:
        return {"success": False, "error": "Missing required parameter: term"}
    
    status_filter = params.get("status")
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    
    # Build query with optional status filter
    status_clause = f' && status == "{status_filter}"' if status_filter else ""
    
    query = f'*[_type == "case" && scotusTerm->slug.current == "{term_slug}"{status_clause}]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, dateDecided, vote, "opinion_author": opinionAuthor->name, sitting, result}}|order(dateDecided desc)|[{offset}...{offset + limit}]'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    cases = []
    for case in result["result"]:
        cases.append({
            "title": case.get("title"),
            "slug": case.get("slug"),
            "docket_number": case.get("docket_number"),
            "status": case.get("status"),
            "date_argued": case.get("dateArgued"),
            "date_decided": case.get("dateDecided"),
            "vote": case.get("vote"),
            "opinion_author": case.get("opinion_author"),
            "sitting": case.get("sitting"),
            "result": case.get("result"),
            "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
        })
    
    # Get total count
    count_query = f'count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}"{status_clause}])'
    count_result = await run_groq_query(count_query)
    total = count_result.get("result", 0) if count_result["success"] else len(cases)
    
    return {
        "success": True,
        "term": term_slug,
        "cases": cases,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def get_term_stats(params: dict) -> dict:
    """Get statistics for a specific term."""
    term_slug = params.get("term")
    if not term_slug:
        return {"success": False, "error": "Missing required parameter: term"}
    
    # Get case counts by status
    stats_query = f'{{"total": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}"]), "decided": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}" && status == "decided"]), "pending": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}" && status == "pending"]), "granted": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}" && status == "granted"]), "denied": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}" && status == "denied"]), "argued": count(*[_type == "case" && scotusTerm->slug.current == "{term_slug}" && defined(dateArgued)])}}'
    
    result = await run_groq_query(stats_query)
    if not result["success"]:
        return result
    
    stats = result["result"]
    
    # Get term info
    term_query = f'*[_type == "scotusTerm" && slug.current == "{term_slug}"][0]{{title, "slug": slug.current, startDate, endDate}}'
    term_result = await run_groq_query(term_query)
    term_info = term_result.get("result", {}) if term_result["success"] else {}
    
    return {
        "success": True,
        "term": term_info,
        "statistics": {
            "total": stats.get("total", 0),
            "decided": stats.get("decided", 0),
            "pending": stats.get("pending", 0),
            "granted": stats.get("granted", 0),
            "denied": stats.get("denied", 0),
            "argued": stats.get("argued", 0),
        },
    }


async def get_case(params: dict) -> dict:
    """Get detailed information about a specific case."""
    case_slug = params.get("slug")
    docket_number = params.get("docket_number")
    include_proceedings = params.get("include_proceedings", True)
    
    if not case_slug and not docket_number:
        return {"success": False, "error": "Missing required parameter: slug or docket_number"}
    
    # Build query based on identifier type
    if case_slug:
        where_clause = f'slug.current == "{case_slug}"'
    else:
        where_clause = f'docketNumber->number == "{docket_number}"'
    
    # Main case query (no sub-projection for proceedings)
    query = f'*[_type == "case" && {where_clause}][0]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, dateDecided, vote, result, resultDetails, sitting, "opinion_author": opinionAuthor->name, "term": scotusTerm->slug.current, holding, judgment, issueArea, supremeCourtPageUrl, opinionLink}}'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    case = result["result"]
    if not case:
        return {
            "success": False,
            "error": f"Case not found: {case_slug or docket_number}",
        }
    
    # Get proceedings separately if requested
    proceedings = None
    if include_proceedings:
        proc_query = f'*[_type == "case" && {where_clause}][0].proceedings{{date, description, color, url}}'
        proc_result = await run_groq_query(proc_query)
        if proc_result["success"] and proc_result.get("result"):
            proceedings = proc_result["result"]
    
    return {"success": True, "case": format_case(case, proceedings)}


async def search_cases(params: dict) -> dict:
    """Search for cases by title, docket number, or keyword."""
    query_text = params.get("query")
    if not query_text:
        return {"success": False, "error": "Missing required parameter: query"}
    
    limit = params.get("limit", 20)
    
    # Build search query - search in title and docket number
    search_query = f'*[_type == "case" && (title match "*{query_text}*" || docketNumber->number match "*{query_text}")]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, dateDecided, vote, "opinion_author": opinionAuthor->name, "term": scotusTerm->slug.current, result}}|order(dateDecided desc)|[0...{limit}]'
    
    result = await run_groq_query(search_query)
    if not result["success"]:
        return result
    
    cases = []
    for case in result["result"]:
        cases.append({
            "title": case.get("title"),
            "slug": case.get("slug"),
            "docket_number": case.get("docket_number"),
            "status": case.get("status"),
            "date_argued": case.get("dateArgued"),
            "date_decided": case.get("dateDecided"),
            "vote": case.get("vote"),
            "opinion_author": case.get("opinion_author"),
            "term": case.get("term"),
            "result": case.get("result"),
            "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
        })
    
    return {
        "success": True,
        "query": query_text,
        "cases": cases,
        "total": len(cases),
    }


async def list_opinion_authors(params: dict) -> dict:
    """List all opinion authors (justices) with case counts."""
    limit = params.get("limit", 50)
    
    query = f'*[_type == "author"]{{name, "slug": slug.current, "case_count": count(*[_type == "case" && opinionAuthor._ref == ^._id])}}|order(case_count desc)|[0...{limit}]'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    authors = []
    for author in result["result"]:
        if author.get("name"):
            authors.append({
                "name": author.get("name"),
                "slug": author.get("slug"),
                "case_count": author.get("case_count", 0),
            })
    
    return {"success": True, "authors": authors}


async def get_cases_by_author(params: dict) -> dict:
    """Get cases written by a specific opinion author."""
    author_name = params.get("author")
    if not author_name:
        return {"success": False, "error": "Missing required parameter: author"}
    
    limit = params.get("limit", 100)
    
    query = f'*[_type == "case" && opinionAuthor->name match "*{author_name}*"]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, dateDecided, vote, "opinion_author": opinionAuthor->name, "term": scotusTerm->slug.current, result}}|order(dateDecided desc)|[0...{limit}]'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    cases = []
    for case in result["result"]:
        cases.append({
            "title": case.get("title"),
            "slug": case.get("slug"),
            "docket_number": case.get("docket_number"),
            "status": case.get("status"),
            "date_argued": case.get("dateArgued"),
            "date_decided": case.get("dateDecided"),
            "vote": case.get("vote"),
            "opinion_author": case.get("opinion_author"),
            "term": case.get("term"),
            "result": case.get("result"),
            "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
        })
    
    return {
        "success": True,
        "author": author_name,
        "cases": cases,
        "total": len(cases),
    }


async def get_recent_decisions(params: dict) -> dict:
    """Get recent Supreme Court decisions."""
    limit = params.get("limit", 10)
    term = params.get("term")
    
    term_clause = f' && scotusTerm->slug.current == "{term}"' if term else ""
    
    query = f'*[_type == "case" && status == "decided" && defined(dateDecided){term_clause}]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, dateDecided, vote, "opinion_author": opinionAuthor->name, "term": scotusTerm->slug.current, result}}|order(dateDecided desc)|[0...{limit}]'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    cases = []
    for case in result["result"]:
        cases.append({
            "title": case.get("title"),
            "slug": case.get("slug"),
            "docket_number": case.get("docket_number"),
            "status": case.get("status"),
            "date_argued": case.get("dateArgued"),
            "date_decided": case.get("dateDecided"),
            "vote": case.get("vote"),
            "opinion_author": case.get("opinion_author"),
            "term": case.get("term"),
            "result": case.get("result"),
            "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
        })
    
    return {
        "success": True,
        "cases": cases,
        "total": len(cases),
    }


async def get_upcoming_arguments(params: dict) -> dict:
    """Get pending/argued cases waiting for decision."""
    limit = params.get("limit", 20)
    term = params.get("term")
    
    term_clause = f' && scotusTerm->slug.current == "{term}"' if term else ""
    
    query = f'*[_type == "case" && status == "pending"{term_clause}]{{title, "slug": slug.current, status, "docket_number": docketNumber->number, dateArgued, "term": scotusTerm->slug.current, sitting}}|order(dateArgued desc)|[0...{limit}]'
    
    result = await run_groq_query(query)
    if not result["success"]:
        return result
    
    cases = []
    for case in result["result"]:
        cases.append({
            "title": case.get("title"),
            "slug": case.get("slug"),
            "docket_number": case.get("docket_number"),
            "status": case.get("status"),
            "date_argued": case.get("dateArgued"),
            "term": case.get("term"),
            "sitting": case.get("sitting"),
            "url": f"https://www.scotusblog.com/cases/{case.get('slug', '')}/",
        })
    
    return {
        "success": True,
        "cases": cases,
        "total": len(cases),
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute SCOTUSblog skill functions.
    
    Dispatches to the appropriate handler based on the 'function' parameter.
    """
    function = params.get("function")
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    handlers = {
        "list_terms": list_terms,
        "get_term_cases": get_term_cases,
        "get_term_stats": get_term_stats,
        "get_case": get_case,
        "search_cases": search_cases,
        "list_opinion_authors": list_opinion_authors,
        "get_cases_by_author": get_cases_by_author,
        "get_recent_decisions": get_recent_decisions,
        "get_upcoming_arguments": get_upcoming_arguments,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: {', '.join(handlers.keys())}",
        }
    
    return await handler(params)


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing list_terms:")
        result = await execute({"function": "list_terms"})
        print(f"  Found {len(result.get('terms', []))} terms")
        for term in result.get('terms', [])[:5]:
            print(f"    {term['title']}: {term['case_count']} cases")
        
        print("\nTesting get_term_stats:")
        result = await execute({"function": "get_term_stats", "term": "ot2024"})
        print(f"  {result}")
        
        print("\nTesting get_term_cases:")
        result = await execute({"function": "get_term_cases", "term": "ot2024", "limit": 5})
        print(f"  Found {len(result.get('cases', []))} cases")
        for case in result.get('cases', [])[:3]:
            print(f"    {case['docket_number']}: {case['title']}")
        
        print("\nTesting get_case:")
        result = await execute({"function": "get_case", "slug": "dewberry-group-inc-v-dewberry-engineers-inc"})
        if result.get("success"):
            case = result.get("case", {})
            print(f"  {case.get('title')}")
            print(f"  Docket: {case.get('docket_number')}")
            print(f"  Status: {case.get('status')}")
            print(f"  Holding: {case.get('holding', '')[:100]}...")
        
        print("\nTesting search_cases:")
        result = await execute({"function": "search_cases", "query": "Dewberry"})
        print(f"  Found {len(result.get('cases', []))} cases")
        
        print("\nTesting get_recent_decisions:")
        result = await execute({"function": "get_recent_decisions", "limit": 3})
        for case in result.get('cases', []):
            print(f"  {case['docket_number']}: {case['title']} ({case['date_decided']})")
    
    asyncio.run(test())