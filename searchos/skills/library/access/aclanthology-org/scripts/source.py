"""
ACL Anthology Access Skill

Fetches structured paper records (title, authors, abstract, PDF link, BibTeX, venue, DOI, etc.)
from the ACL Anthology at aclanthology.org.

Supports:
- get_paper: Fetch a single paper by its Anthology ID (e.g., "2024.acl-long.788")
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status} for {url}")
        return await resp.text()


async def _fetch_text(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch text content from a URL, returning status and text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/plain,text/html,application/xml",
    }
    async with session.get(url, headers=headers) as resp:
        return resp.status, await resp.text()


def _parse_paper_page(html: str, anthology_id: str) -> dict[str, Any]:
    """Parse the ACL Anthology paper page HTML to extract structured metadata."""
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "anthology_id": anthology_id,
        "url": f"https://aclanthology.org/{anthology_id}/",
        "success": True,
        "error": None,
    }
    
    # Extract title from h2#title or meta tag
    title_elem = soup.find("h2", id="title")
    if title_elem:
        result["title"] = title_elem.get_text(strip=True)
    else:
        meta_title = soup.find("meta", {"name": "citation_title"})
        if meta_title:
            result["title"] = meta_title.get("content", "").strip()
    
    # Extract authors from meta tags
    author_metas = soup.find_all("meta", {"name": "citation_author"})
    if author_metas:
        result["authors"] = [m.get("content", "").strip() for m in author_metas]
    
    # Extract abstract
    abstract_div = soup.find("div", class_="acl-abstract")
    if abstract_div:
        abstract_text = abstract_div.get_text(separator=" ", strip=True)
        # Remove "Abstract" prefix if present
        if abstract_text.startswith("Abstract"):
            abstract_text = abstract_text[8:].strip()
        result["abstract"] = abstract_text
    
    # Extract PDF URL
    meta_pdf = soup.find("meta", {"name": "citation_pdf_url"})
    if meta_pdf:
        result["pdf_url"] = meta_pdf.get("content", "").strip()
    
    # Extract DOI
    meta_doi = soup.find("meta", {"name": "citation_doi"})
    if meta_doi:
        result["doi"] = meta_doi.get("content", "").strip()
    
    # Extract publication date
    meta_pub_date = soup.find("meta", {"name": "citation_publication_date"})
    if meta_pub_date:
        result["publication_date"] = meta_pub_date.get("content", "").strip()
    
    # Extract conference/volume title
    meta_conf = soup.find("meta", {"name": "citation_conference_title"})
    if meta_conf:
        result["venue"] = meta_conf.get("content", "").strip()
    
    # Extract page numbers
    meta_firstpage = soup.find("meta", {"name": "citation_firstpage"})
    meta_lastpage = soup.find("meta", {"name": "citation_lastpage"})
    if meta_firstpage and meta_lastpage:
        result["pages"] = f"{meta_firstpage.get('content', '')}–{meta_lastpage.get('content', '')}"
    
    # Extract additional metadata from dt/dd pairs
    dts = soup.find_all("dt")
    for dt in dts:
        dt_text = dt.get_text(strip=True).rstrip(":")
        dd = dt.find_next_sibling("dd")
        if dd:
            dd_text = dd.get_text(strip=True)
            
            if dt_text == "Anthology ID":
                result["anthology_id"] = dd_text
            elif dt_text == "Year":
                result["year"] = dd_text
            elif dt_text == "Month":
                result["month"] = dd_text
            elif dt_text == "Address":
                result["address"] = dd_text
            elif dt_text == "Editors":
                result["editors"] = [e.strip() for e in dd_text.split(",")]
            elif dt_text == "Publisher":
                result["publisher"] = dd_text
            elif dt_text == "Bibkey":
                result["bibkey"] = dd_text
            elif dt_text == "Award":
                result["award"] = dd_text
            elif dt_text == "Video":
                result["video_url"] = dd_text
    
    # BibTeX URL
    result["bibtex_url"] = f"https://aclanthology.org/{anthology_id}.bib"
    
    return result


async def get_paper(anthology_id: str, include_bibtex: bool = False) -> dict[str, Any]:
    """
    Fetch a paper from ACL Anthology by its Anthology ID.
    
    Args:
        anthology_id: The ACL Anthology ID (e.g., "2024.acl-long.788" or "P02-1040")
        include_bibtex: Whether to fetch and include the BibTeX citation
    
    Returns:
        Dictionary with paper metadata or error information
    """
    # Normalize the ID (remove leading/trailing slashes, .pdf extension)
    anthology_id = anthology_id.strip().strip("/")
    if anthology_id.endswith(".pdf"):
        anthology_id = anthology_id[:-4]
    
    # Validate ID format - supports both modern and legacy formats
    # Modern: YYYY.venue-type.number (e.g., 2024.acl-long.788)
    # Legacy: XYY-NNNN (e.g., P02-1040)
    modern_pattern = r"^\d{4}\.[a-z0-9-]+\.\d+$"
    legacy_pattern = r"^[A-Z]\d{2}-\d{4}$"
    
    if not (re.match(modern_pattern, anthology_id) or re.match(legacy_pattern, anthology_id)):
        return {
            "success": False,
            "error": f"Invalid anthology ID format: {anthology_id}. Expected format like '2024.acl-long.788' or 'P02-1040'",
            "anthology_id": anthology_id,
        }
    
    paper_url = f"https://aclanthology.org/{anthology_id}/"
    
    async with aiohttp.ClientSession() as session:
        try:
            # Fetch the paper page
            html = await _fetch_html(paper_url, session)
            result = _parse_paper_page(html, anthology_id)
            
            # Optionally fetch BibTeX
            if include_bibtex:
                bibtex_url = f"https://aclanthology.org/{anthology_id}.bib"
                status, bibtex = await _fetch_text(bibtex_url, session)
                if status == 200:
                    result["bibtex"] = bibtex
                else:
                    result["bibtex"] = None
                    result["bibtex_error"] = f"Failed to fetch BibTeX (HTTP {status})"
            
            return result
            
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "anthology_id": anthology_id,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {type(e).__name__}: {e}",
                "anthology_id": anthology_id,
            }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the ACL Anthology access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ("get_paper")
            - anthology_id: The ACL Anthology ID (for get_paper)
            - include_bibtex: Whether to include BibTeX (optional, for get_paper)

    
    Returns:
        Dictionary with the result of the operation
    """
    function = params.get("function")
    
    if function == "get_paper":
        anthology_id = params.get("anthology_id")
        if not anthology_id:
            return {
                "success": False,
                "error": "Missing required parameter: anthology_id",
            }
        
        include_bibtex = params.get("include_bibtex", False)
        return await get_paper(anthology_id, include_bibtex)
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported functions: get_paper",
        }