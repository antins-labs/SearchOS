"""
DOI.org Metadata Access Skill

Retrieves structured metadata from DOI landing pages via content negotiation.
Supports both CrossRef CSL JSON format (for publications) and ScienceBase JSON 
format (for datasets/data releases).
"""

from __future__ import annotations
import aiohttp
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute DOI metadata lookup.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with structured metadata or error information
    """
    function = params.get("function", "")
    
    if function == "get_metadata":
        return await get_metadata(params)
    elif function == "list_files":
        return await list_files(params)
    elif function == "resolve_doi":
        return await resolve_doi(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def _fetch_doi_metadata(doi: str, accept_header: str = "application/json") -> tuple[int, dict | str, str]:
    """
    Fetch metadata from DOI.org with content negotiation.
    
    Returns:
        Tuple of (status_code, json_data_or_text, final_url)
    """
    url = f"https://doi.org/{doi}"
    headers = {
        'Accept': accept_header,
        'User-Agent': 'SearchOS-DOI-Skill/1.0 (mailto:searchos@example.org)'
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers, allow_redirects=True) as response:
            final_url = str(response.url)
            content_type = response.headers.get('Content-Type', '')
            
            if 'json' in content_type.lower():
                data = await response.json()
                return response.status, data, final_url
            else:
                text = await response.text()
                return response.status, text, final_url


async def get_metadata(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve comprehensive metadata for a DOI.
    
    Attempts to get the richest metadata format available:
    1. First tries application/json (may return ScienceBase format for datasets)
    2. Falls back to CSL JSON format for publications
    
    Args:
        params: Must include 'doi' (e.g., "10.5066/P13XCP3R")
    
    Returns:
        Dictionary with normalized metadata fields
    """
    doi = params.get("doi", "").strip()
    if not doi:
        return {"error": "Missing required parameter: doi", "success": False}
    
    # Clean DOI - remove 'doi:' prefix if present
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    
    try:
        # First try application/json (works for ScienceBase and some others)
        status, data, final_url = await _fetch_doi_metadata(doi, "application/json")
        
        if status == 200 and isinstance(data, dict):
            # Check if this looks like ScienceBase format
            if "sciencebase.gov" in final_url or "identifiers" in data:
                return _normalize_sciencebase_metadata(data, final_url, doi)
            # Check if this looks like CrossRef CSL JSON
            if "DOI" in data and ("author" in data or "title" in data):
                return _normalize_crossref_metadata(data, final_url, doi)
            # Unknown format, return as-is with basic normalization
            return _normalize_generic_metadata(data, final_url, doi)
        
        # Fall back to CSL JSON for publications
        status, data, final_url = await _fetch_doi_metadata(doi, "application/vnd.citationstyles.csl+json")
        
        if status == 200 and isinstance(data, dict):
            return _normalize_crossref_metadata(data, final_url, doi)
        
        if status != 200:
            return {
                "error": f"DOI lookup failed with status {status}",
                "success": False,
                "doi": doi
            }
        
        return {
            "error": "Could not retrieve structured metadata",
            "success": False,
            "doi": doi,
            "final_url": final_url
        }
        
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False, "doi": doi}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False, "doi": doi}


def _normalize_sciencebase_metadata(data: dict, final_url: str, doi: str) -> dict[str, Any]:
    """
    Normalize ScienceBase-style metadata to a consistent format.
    """
    result = {
        "success": True,
        "doi": doi,
        "final_url": final_url,
        "source_type": "sciencebase",
        "title": data.get("title", ""),
        "summary": data.get("summary") or data.get("body", ""),
        "citation": data.get("citation", ""),
        "purpose": data.get("purpose", ""),
    }
    
    # Extract identifiers
    identifiers = data.get("identifiers", [])
    for ident in identifiers:
        if ident.get("type") == "DOI":
            result["doi"] = ident.get("key", "").replace("doi:", "")
    
    # Extract contacts/authors
    contacts = data.get("contacts", [])
    result["contacts"] = []
    result["authors"] = []
    
    for contact in contacts:
        contact_info = {
            "name": contact.get("name", ""),
            "type": contact.get("type", ""),
            "email": contact.get("email", ""),
            "organization": contact.get("organization", {}).get("displayText", "") if isinstance(contact.get("organization"), dict) else "",
        }
        result["contacts"].append(contact_info)
        
        # Extract authors from contacts
        if contact.get("type") in ["Originator", "Author", "Point of Contact"]:
            if contact.get("name"):
                result["authors"].append(contact["name"])
    
    # Extract dates
    dates = data.get("dates", [])
    result["dates"] = {}
    for date_entry in dates:
        date_type = date_entry.get("type", "").lower()
        date_str = date_entry.get("dateString", "")
        if date_type and date_str:
            result["dates"][date_type] = date_str
    
    # Extract tags/keywords
    tags = data.get("tags", [])
    result["keywords"] = [tag.get("name", "") for tag in tags if tag.get("name")]
    
    # Extract web links
    web_links = data.get("webLinks", [])
    result["links"] = []
    for link in web_links:
        result["links"].append({
            "type": link.get("type", ""),
            "title": link.get("title", ""),
            "url": link.get("uri", "")
        })
    
    # Extract provenance
    provenance = data.get("provenance", {})
    if provenance:
        result["provenance"] = {
            "created": provenance.get("dateCreated", ""),
            "updated": provenance.get("lastUpdated", ""),
            "annotation": provenance.get("annotation", "")
        }
    
    # Extract system types
    result["system_types"] = data.get("systemTypes", [])
    
    # ScienceBase-specific IDs
    if "id" in data:
        result["source_id"] = data["id"]
    
    return result


def _normalize_crossref_metadata(data: dict, final_url: str, doi: str) -> dict[str, Any]:
    """
    Normalize CrossRef CSL JSON metadata to a consistent format.
    """
    result = {
        "success": True,
        "doi": data.get("DOI", doi),
        "final_url": final_url,
        "source_type": "crossref",
        "title": data.get("title", ""),
        "summary": data.get("abstract", ""),
        "citation": None,  # CSL doesn't include pre-formatted citation
    }
    
    # Extract type
    result["publication_type"] = data.get("type", "")
    
    # Extract authors
    authors = data.get("author", [])
    result["authors"] = []
    result["contacts"] = []
    
    for author in authors:
        given = author.get("given", "")
        family = author.get("family", "")
        name = f"{given} {family}".strip()
        result["authors"].append(name)
        
        contact_info = {"name": name, "type": "author"}
        if author.get("affiliation"):
            affs = author["affiliation"]
            if isinstance(affs, list) and len(affs) > 0:
                contact_info["affiliation"] = affs[0].get("name", "") if isinstance(affs[0], dict) else str(affs[0])
        result["contacts"].append(contact_info)
    
    # Extract dates
    result["dates"] = {}
    
    # Published date - try multiple fields
    published = data.get("published") or data.get("published-print") or data.get("published-online") or data.get("issued", {})
    if published and isinstance(published, dict) and "date-parts" in published:
        parts = published["date-parts"]
        if isinstance(parts, list) and len(parts) > 0:
            parts = parts[0]
            if isinstance(parts, list) and len(parts) > 0:
                result["dates"]["publication"] = "-".join(str(p) for p in parts)
    
    # Other dates
    for key in ["created", "deposited", "indexed"]:
        if key in data:
            date_info = data[key]
            if isinstance(date_info, dict) and "date-parts" in date_info:
                parts = date_info["date-parts"]
                if isinstance(parts, list) and len(parts) > 0:
                    parts = parts[0]
                    if isinstance(parts, list) and len(parts) > 0:
                        result["dates"][key] = "-".join(str(p) for p in parts)
    
    # Extract container (journal) info
    container = data.get("container-title", [])
    if isinstance(container, list) and container:
        result["journal"] = container[0]
    elif isinstance(container, str):
        result["journal"] = container
    
    # Volume, issue, pages
    if "volume" in data:
        result["volume"] = data["volume"]
    if "issue" in data:
        result["issue"] = data["issue"]
    if "page" in data:
        result["pages"] = data["page"]
    
    # Extract links
    result["links"] = []
    
    # Resource link
    if "resource" in data:
        resource = data["resource"]
        if isinstance(resource, dict):
            primary = resource.get("primary", {})
            if isinstance(primary, dict) and "URL" in primary:
                result["links"].append({"type": "resource", "url": primary["URL"]})
        elif isinstance(resource, str):
            result["links"].append({"type": "resource", "url": resource})
    
    # Other links
    links = data.get("link", [])
    for link in links if isinstance(links, list) else []:
        result["links"].append({
            "type": link.get("content-type", "link"),
            "url": link.get("URL", "")
        })
    
    # URL field
    if "URL" in data:
        result["links"].append({"type": "doi_landing", "url": data["URL"]})
    
    # Subjects/keywords
    subjects = data.get("subject", [])
    result["keywords"] = subjects if isinstance(subjects, list) else [subjects] if subjects else []
    
    # Reference count
    if "is-referenced-by-count" in data:
        result["citation_count"] = data["is-referenced-by-count"]
    
    # Publisher
    result["publisher"] = data.get("publisher", "")
    
    # ISSN/ISBN
    issn = data.get("ISSN", [])
    if issn:
        result["issn"] = issn[0] if isinstance(issn, list) else issn
    
    return result


def _normalize_generic_metadata(data: dict, final_url: str, doi: str) -> dict[str, Any]:
    """
    Normalize unknown/other metadata formats to a consistent format.
    """
    result = {
        "success": True,
        "doi": doi,
        "final_url": final_url,
        "source_type": "unknown",
        "title": data.get("title", ""),
        "summary": data.get("summary") or data.get("abstract") or data.get("description", ""),
    }
    
    # Try to extract common fields
    if "author" in data:
        result["authors"] = []
        for author in data["author"] if isinstance(data["author"], list) else [data["author"]]:
            if isinstance(author, dict):
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if not name:
                    name = author.get("name", "")
            else:
                name = str(author)
            if name:
                result["authors"].append(name)
    
    if "publisher" in data:
        result["publisher"] = data["publisher"]
    
    if "type" in data:
        result["publication_type"] = data["type"]
    
    # Pass through any remaining data
    result["raw_metadata"] = data
    
    return result


async def list_files(params: dict[str, Any]) -> dict[str, Any]:
    """
    List downloadable files associated with a DOI.
    
    Works best with ScienceBase-hosted datasets. For publication DOIs,
    may return limited or no file information.
    
    Args:
        params: Must include 'doi' (e.g., "10.5066/P13XCP3R")
    
    Returns:
        Dictionary with list of files including download URLs
    """
    doi = params.get("doi", "").strip()
    if not doi:
        return {"error": "Missing required parameter: doi", "success": False}
    
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    
    try:
        status, data, final_url = await _fetch_doi_metadata(doi, "application/json")
        
        if status != 200 or not isinstance(data, dict):
            return {
                "error": f"Could not retrieve metadata for files (status {status})",
                "success": False,
                "doi": doi
            }
        
        files = data.get("files", [])
        
        if not files:
            # Check distribution links for downloads
            dist_links = data.get("distributionLinks", [])
            for dl in dist_links:
                if dl.get("type") == "downloadLink":
                    files.append({
                        "name": dl.get("name", ""),
                        "url": dl.get("uri", ""),
                        "title": dl.get("title", "")
                    })
        
        result = {
            "success": True,
            "doi": doi,
            "title": data.get("title", ""),
            "file_count": len(files),
            "files": []
        }
        
        for f in files:
            file_info = {
                "name": f.get("name", ""),
                "title": f.get("title"),
                "content_type": f.get("contentType", ""),
                "size_bytes": f.get("size"),
                "url": f.get("url") or f.get("downloadUri") or f.get("uri", ""),
                "date_uploaded": f.get("dateUploaded", ""),
            }
            
            # Add checksum if available
            checksum = f.get("checksum", {})
            if checksum:
                file_info["checksum"] = {
                    "value": checksum.get("value", ""),
                    "type": checksum.get("type", "")
                }
            
            result["files"].append(file_info)
        
        return result
        
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False, "doi": doi}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False, "doi": doi}


async def resolve_doi(params: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve a DOI to its final landing page URL.
    
    Args:
        params: Must include 'doi' (e.g., "10.5066/P13XCP3R")
    
    Returns:
        Dictionary with the resolved URL and basic info
    """
    doi = params.get("doi", "").strip()
    if not doi:
        return {"error": "Missing required parameter: doi", "success": False}
    
    doi = doi.replace("doi:", "").replace("DOI:", "").strip()
    
    try:
        url = f"https://doi.org/{doi}"
        headers = {
            'User-Agent': 'SearchOS-DOI-Skill/1.0'
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Use HEAD request for efficiency
            async with session.head(url, headers=headers, allow_redirects=True) as response:
                final_url = str(response.url)
                return {
                    "success": True,
                    "doi": doi,
                    "doi_url": f"https://doi.org/{doi}",
                    "resolved_url": final_url,
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type", "")
                }
                
    except aiohttp.ClientError as e:
        return {"error": f"Network error: {str(e)}", "success": False, "doi": doi}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False, "doi": doi}