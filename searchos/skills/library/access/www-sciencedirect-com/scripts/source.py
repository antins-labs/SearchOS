"""
ScienceDirect Article Access Skill

This skill retrieves academic article metadata from ScienceDirect/Elsevier publications
using open APIs that provide access to the same content, since ScienceDirect.com
blocks direct web scraping with 403 errors.

Data sources:
- OpenAlex API: Comprehensive metadata, abstracts (inverted index), citations
- Semantic Scholar API: Citations, open access PDFs, authors
- CrossRef API: Bibliographic data, references
- Elsevier API: Publisher metadata (limited without API key)
"""

import asyncio
import aiohttp
import re
from typing import Any, Optional


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute ScienceDirect article access functions.
    
    Functions:
    - get_article: Get article by DOI or PII
    - search_articles: Search for articles by query
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "search_articles":
        return await search_articles(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get article metadata by DOI or PII.
    
    Parameters:
    - doi: Digital Object Identifier (e.g., "10.1016/j.tust.2021.104281")
    - pii: Publisher Item Identifier (e.g., "S0886779821004727")
    - include_abstract: Include abstract in response (default: true)
    - include_references: Include references (default: false)
    """
    doi = params.get("doi", "").strip()
    pii = params.get("pii", "").strip()
    include_abstract = params.get("include_abstract", True)
    include_references = params.get("include_references", False)
    
    if not doi and not pii:
        return {"error": "Either 'doi' or 'pii' parameter is required"}
    
    # Normalize DOI - remove URL prefix if present
    if doi:
        doi = doi.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ScienceDirectSkill/1.0)",
        "Accept": "application/json",
    }
    
    result = {
        "doi": doi,
        "pii": pii,
        "sources": [],
        "data": {}
    }
    
    async with aiohttp.ClientSession() as session:
        # 1. OpenAlex API - most comprehensive
        openalex_data = await _fetch_openalex(session, headers, doi, pii)
        if openalex_data and not openalex_data.get("error"):
            result["sources"].append("openalex")
            result["data"]["openalex"] = _extract_openalex_data(openalex_data, include_abstract)
        
        # 2. Semantic Scholar API - citations and open access
        s2_data = await _fetch_semantic_scholar(session, headers, doi)
        if s2_data and not s2_data.get("error"):
            result["sources"].append("semantic_scholar")
            result["data"]["semantic_scholar"] = _extract_s2_data(s2_data)
        
        # 3. CrossRef API - bibliographic data
        crossref_data = await _fetch_crossref(session, headers, doi)
        if crossref_data and not crossref_data.get("error"):
            result["sources"].append("crossref")
            result["data"]["crossref"] = _extract_crossref_data(crossref_data, include_references)
        
        # 4. Elsevier API - publisher data (limited without API key)
        elsevier_data = await _fetch_elsevier(session, headers, pii, doi)
        if elsevier_data and not elsevier_data.get("error"):
            result["sources"].append("elsevier")
            result["data"]["elsevier"] = _extract_elsevier_data(elsevier_data)
    
    # Merge into unified view
    if result["sources"]:
        result["article"] = _merge_article_data(result["data"])
        result["success"] = True
    else:
        result["error"] = "No data sources returned results"
        result["success"] = False
    
    return result


async def search_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for articles by query.
    
    Parameters:
    - query: Search query string
    - limit: Maximum results to return (default: 10, max: 50)
    - source: API to use - "openalex" (default), "crossref", or "all"
    """
    query = params.get("query", "").strip()
    limit = min(int(params.get("limit", 10)), 50)
    source = params.get("source", "openalex")
    
    if not query:
        return {"error": "Query parameter is required"}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ScienceDirectSkill/1.0)",
        "Accept": "application/json",
    }
    
    results = {
        "query": query,
        "limit": limit,
        "source": source,
        "articles": [],
        "success": False
    }
    
    async with aiohttp.ClientSession() as session:
        if source in ["openalex", "all"]:
            openalex_results = await _search_openalex(session, headers, query, limit)
            if isinstance(openalex_results, list):
                results["articles"].extend(openalex_results)
        
        if source in ["crossref", "all"]:
            crossref_results = await _search_crossref(session, headers, query, limit)
            if isinstance(crossref_results, list):
                results["articles"].extend(crossref_results)
    
    # Deduplicate by DOI
    seen_dois = set()
    unique_articles = []
    for article in results["articles"]:
        doi = article.get("doi", "")
        if doi and doi not in seen_dois:
            seen_dois.add(doi)
            unique_articles.append(article)
        elif not doi:
            unique_articles.append(article)
    
    results["articles"] = unique_articles[:limit]
    results["total_returned"] = len(results["articles"])
    results["success"] = len(results["articles"]) > 0
    
    return results


# ============================================================================
# API Fetch Functions
# ============================================================================

async def _fetch_openalex(session: aiohttp.ClientSession, headers: dict, doi: str, pii: str) -> Optional[dict]:
    """Fetch article from OpenAlex API."""
    try:
        if doi:
            url = f"https://api.openalex.org/works/https://doi.org/{doi}"
        elif pii:
            # Try to find by PII - need to search
            url = f"https://api.openalex.org/works?filter=ids.pii:{pii}"
        else:
            return None
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                # If search results, get first item
                if "results" in data:
                    results = data.get("results", [])
                    if results:
                        return results[0]
                    return None
                return data
    except Exception as e:
        return {"error": str(e)}
    return None


async def _fetch_semantic_scholar(session: aiohttp.ClientSession, headers: dict, doi: str) -> Optional[dict]:
    """Fetch article from Semantic Scholar API."""
    if not doi:
        return None
    
    try:
        fields = "title,abstract,authors,year,venue,citationCount,publicationTypes,openAccessPdf,url"
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={fields}"
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        return {"error": str(e)}
    return None


async def _fetch_crossref(session: aiohttp.ClientSession, headers: dict, doi: str) -> Optional[dict]:
    """Fetch article from CrossRef API."""
    if not doi:
        return None
    
    try:
        url = f"https://api.crossref.org/works/{doi}"
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("message", {})
    except Exception as e:
        return {"error": str(e)}
    return None


async def _fetch_elsevier(session: aiohttp.ClientSession, headers: dict, pii: str, doi: str) -> Optional[dict]:
    """Fetch article from Elsevier API (limited without API key)."""
    try:
        if pii:
            url = f"https://api.elsevier.com/content/article/pii/{pii}"
        elif doi:
            url = f"https://api.elsevier.com/content/article/doi/{doi}"
        else:
            return None
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("full-text-retrieval-response", {})
    except Exception as e:
        return {"error": str(e)}
    return None


async def _search_openalex(session: aiohttp.ClientSession, headers: dict, query: str, limit: int) -> list:
    """Search OpenAlex for articles."""
    try:
        url = f"https://api.openalex.org/works?search={query}&per_page={limit}"
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                articles = []
                for work in data.get("results", []):
                    article = {
                        "title": work.get("title"),
                        "doi": work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
                        "year": work.get("publication_year"),
                        "type": work.get("type"),
                        "source": "openalex",
                        "open_access": work.get("open_access", {}).get("is_oa", False),
                        "cited_by_count": work.get("cited_by_count"),
                        "url": work.get("id"),
                    }
                    
                    # Authors
                    authorships = work.get("authorships", [])
                    article["authors"] = [
                        a.get("author", {}).get("display_name") 
                        for a in authorships[:5]
                    ]
                    
                    # Venue
                    primary_loc = work.get("primary_location", {})
                    if primary_loc:
                        source = primary_loc.get("source", {})
                        article["venue"] = source.get("display_name") if source else None
                    
                    articles.append(article)
                return articles
    except Exception:
        pass
    return []


async def _search_crossref(session: aiohttp.ClientSession, headers: dict, query: str, limit: int) -> list:
    """Search CrossRef for articles."""
    try:
        url = f"https://api.crossref.org/works?query={query}&rows={limit}"
        
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json()
                articles = []
                for item in data.get("message", {}).get("items", []):
                    titles = item.get("title", [])
                    authors_list = item.get("author", [])
                    
                    article = {
                        "title": titles[0] if titles else None,
                        "doi": item.get("DOI"),
                        "year": item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                        "type": item.get("type"),
                        "source": "crossref",
                        "publisher": item.get("publisher"),
                        "url": f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None,
                    }
                    
                    # Authors
                    article["authors"] = [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in authors_list[:5]
                    ]
                    
                    articles.append(article)
                return articles
    except Exception:
        pass
    return []


# ============================================================================
# Data Extraction Functions
# ============================================================================

def _extract_openalex_data(data: dict, include_abstract: bool) -> dict:
    """Extract relevant fields from OpenAlex response."""
    result = {
        "id": data.get("id"),
        "title": data.get("title"),
        "doi": data.get("doi", "").replace("https://doi.org/", "") if data.get("doi") else None,
        "year": data.get("publication_year"),
        "type": data.get("type"),
        "cited_by_count": data.get("cited_by_count"),
        "is_retracted": data.get("is_retracted"),
        "language": data.get("language"),
        "open_access": data.get("open_access", {}),
    }
    
    # Authors
    authorships = data.get("authorships", [])
    result["authors"] = [
        {
            "name": a.get("author", {}).get("display_name"),
            "orcid": a.get("author", {}).get("orcid"),
            "affiliations": [inst.get("display_name") for inst in a.get("institutions", [])[:2]]
        }
        for a in authorships
    ]
    
    # Venue/Journal
    primary_loc = data.get("primary_location", {})
    if primary_loc:
        source = primary_loc.get("source", {})
        result["venue"] = {
            "name": source.get("display_name"),
            "type": source.get("type"),
            "issn": source.get("issn_l"),
        }
    
    # Abstract (from inverted index)
    if include_abstract:
        abstract_inverted = data.get("abstract_inverted_index")
        if abstract_inverted:
            positions = {}
            for word, pos_list in abstract_inverted.items():
                for pos in pos_list:
                    positions[pos] = word
            result["abstract"] = " ".join(positions[i] for i in sorted(positions.keys()))
    
    # Keywords/Topics
    topics = data.get("topics", [])
    result["topics"] = [t.get("display_name") for t in topics[:5]]
    
    keywords = data.get("keywords", [])
    result["keywords"] = [k.get("display_name") for k in keywords[:10]]
    
    # Sustainable Development Goals
    sdgs = data.get("sustainable_development_goals", [])
    result["sdgs"] = [s.get("display_name") for s in sdgs]
    
    return result


def _extract_s2_data(data: dict) -> dict:
    """Extract relevant fields from Semantic Scholar response."""
    result = {
        "paper_id": data.get("paperId"),
        "title": data.get("title"),
        "year": data.get("year"),
        "venue": data.get("venue"),
        "citation_count": data.get("citationCount"),
        "publication_types": data.get("publicationTypes", []),
        "url": data.get("url"),
    }
    
    # Authors
    authors = data.get("authors", [])
    result["authors"] = [
        {
            "name": a.get("name"),
            "author_id": a.get("authorId"),
        }
        for a in authors
    ]
    
    # Abstract
    if data.get("abstract"):
        result["abstract"] = data.get("abstract")
    
    # Open Access PDF
    oa_pdf = data.get("openAccessPdf")
    if oa_pdf:
        result["open_access_pdf"] = {
            "url": oa_pdf.get("url"),
            "status": oa_pdf.get("status"),
            "license": oa_pdf.get("license"),
        }
    
    return result


def _extract_crossref_data(data: dict, include_references: bool) -> dict:
    """Extract relevant fields from CrossRef response."""
    titles = data.get("title", [])
    authors_list = data.get("author", [])
    
    result = {
        "title": titles[0] if titles else None,
        "doi": data.get("DOI"),
        "type": data.get("type"),
        "publisher": data.get("publisher"),
        "published": data.get("published-print", {}).get("date-parts", [[None]])[0],
        "is_referenced_by_count": data.get("is-referenced-by-count"),
        "references_count": data.get("references-count"),
    }
    
    # Authors
    result["authors"] = [
        {
            "given": a.get("given"),
            "family": a.get("family"),
            "orcid": a.get("ORCID"),
            "affiliation": a.get("affiliation", [{}])[0].get("name") if a.get("affiliation") else None,
        }
        for a in authors_list
    ]
    
    # Container (journal)
    container = data.get("container-title", [])
    if container:
        result["journal"] = container[0]
    
    # ISSN
    issn = data.get("ISSN", [])
    if issn:
        result["issn"] = issn
    
    # Volume/Issue/Pages
    result["volume"] = data.get("volume")
    result["issue"] = data.get("issue")
    result["page"] = data.get("page")
    
    # References
    if include_references:
        refs = data.get("reference", [])
        result["references"] = [
            {
                "key": r.get("key"),
                "doi": r.get("DOI"),
                "unstructured": r.get("unstructured"),
                "author": r.get("author"),
                "year": r.get("year"),
                "title": r.get("article-title"),
            }
            for r in refs
        ]
    
    # License
    licenses = data.get("license", [])
    if licenses:
        result["license"] = [
            {
                "url": lic.get("URL"),
                "version": lic.get("content-version"),
            }
            for lic in licenses
        ]
    
    return result


def _extract_elsevier_data(data: dict) -> dict:
    """Extract relevant fields from Elsevier API response."""
    coredata = data.get("coredata", {})
    
    result = {
        "title": coredata.get("dc:title"),
        "doi": coredata.get("prism:doi"),
        "pii": coredata.get("pii"),
        "eid": coredata.get("eid"),
        "publication_name": coredata.get("prism:publicationName"),
        "aggregation_type": coredata.get("prism:aggregationType"),
        "cover_date": coredata.get("prism:coverDate"),
        "cover_display_date": coredata.get("prism:coverDisplayDate"),
        "issn": coredata.get("prism:issn"),
        "open_access": coredata.get("openaccessArticle"),
        "open_access_type": coredata.get("openaccessType"),
        "open_access_license": coredata.get("openaccessUserLicense"),
    }
    
    # Links
    links = coredata.get("link", [])
    if links:
        result["links"] = [
            {
                "url": link.get("@href"),
                "rel": link.get("@rel"),
            }
            for link in links
        ]
    
    return result


def _merge_article_data(data: dict) -> dict:
    """Merge data from multiple sources into unified article object."""
    merged = {
        "title": None,
        "doi": None,
        "pii": None,
        "year": None,
        "authors": [],
        "abstract": None,
        "journal": None,
        "venue": None,
        "type": None,
        "publisher": None,
        "citation_count": None,
        "is_open_access": False,
        "open_access_pdf_url": None,
        "keywords": [],
        "topics": [],
        "url": None,
    }
    
    # Priority order: OpenAlex > Semantic Scholar > CrossRef > Elsevier
    
    # OpenAlex
    if "openalex" in data:
        oa = data["openalex"]
        merged["title"] = merged["title"] or oa.get("title")
        merged["doi"] = merged["doi"] or oa.get("doi")
        merged["year"] = merged["year"] or oa.get("year")
        merged["type"] = merged["type"] or oa.get("type")
        merged["citation_count"] = merged["citation_count"] or oa.get("cited_by_count")
        merged["abstract"] = merged["abstract"] or oa.get("abstract")
        merged["keywords"] = merged["keywords"] or oa.get("keywords", [])
        merged["topics"] = merged["topics"] or oa.get("topics", [])
        merged["url"] = merged["url"] or oa.get("id")
        
        if oa.get("authors"):
            merged["authors"] = oa["authors"]
        
        if oa.get("venue"):
            merged["venue"] = oa["venue"].get("name")
            merged["journal"] = merged["journal"] or merged["venue"]
        
        if oa.get("open_access"):
            merged["is_open_access"] = oa["open_access"].get("is_oa", False)
    
    # Semantic Scholar
    if "semantic_scholar" in data:
        s2 = data["semantic_scholar"]
        merged["title"] = merged["title"] or s2.get("title")
        merged["year"] = merged["year"] or s2.get("year")
        merged["venue"] = merged["venue"] or s2.get("venue")
        merged["journal"] = merged["journal"] or merged["venue"]
        merged["abstract"] = merged["abstract"] or s2.get("abstract")
        merged["url"] = merged["url"] or s2.get("url")
        
        if not merged["authors"] and s2.get("authors"):
            merged["authors"] = [{"name": a.get("name")} for a in s2["authors"]]
        
        if s2.get("citation_count"):
            merged["citation_count"] = s2["citation_count"]
        
        if s2.get("open_access_pdf"):
            merged["is_open_access"] = True
            merged["open_access_pdf_url"] = s2["open_access_pdf"].get("url")
    
    # CrossRef
    if "crossref" in data:
        cr = data["crossref"]
        merged["title"] = merged["title"] or cr.get("title")
        merged["doi"] = merged["doi"] or cr.get("doi")
        merged["type"] = merged["type"] or cr.get("type")
        merged["publisher"] = cr.get("publisher")
        
        if cr.get("published"):
            merged["year"] = merged["year"] or cr["published"][0]
        
        if not merged["authors"] and cr.get("authors"):
            merged["authors"] = [
                {"name": f"{a.get('given', '')} {a.get('family', '')}".strip()}
                for a in cr["authors"]
            ]
        
        if cr.get("journal"):
            merged["journal"] = merged["journal"] or cr["journal"]
            merged["venue"] = merged["venue"] or cr["journal"]
        
        if cr.get("is_referenced_by_count") and not merged["citation_count"]:
            merged["citation_count"] = cr["is_referenced_by_count"]
    
    # Elsevier
    if "elsevier" in data:
        els = data["elsevier"]
        merged["title"] = merged["title"] or els.get("title")
        merged["doi"] = merged["doi"] or els.get("doi")
        merged["pii"] = merged["pii"] or els.get("pii")
        merged["publisher"] = merged["publisher"] or "Elsevier"
        
        if els.get("publication_name"):
            merged["journal"] = merged["journal"] or els["publication_name"]
            merged["venue"] = merged["venue"] or els["publication_name"]
        
        if els.get("cover_date"):
            try:
                merged["year"] = merged["year"] or int(els["cover_date"][:4])
            except (ValueError, TypeError):
                pass
        
        if els.get("open_access"):
            merged["is_open_access"] = True
    
    # Clean up None values
    merged = {k: v for k, v in merged.items() if v is not None}
    
    return merged