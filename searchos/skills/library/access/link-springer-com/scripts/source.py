"""
Springer Link article and issue extractor.

Provides structured access to:
- Article metadata (via DOI or URL)
- Issue/Volume listings with article summaries
- Journal information

Uses direct HTTP requests with HTML parsing (no API required).
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a Springer Link query.
    
    Args:
        params: Must contain 'function' key with one of:
            - 'get_article': Extract article metadata
            - 'get_issue': Get articles from a specific journal issue
            - 'list_issues': List available issues for a journal
        
        For 'get_article':
            - 'doi' (required): DOI like '10.1057/s41290-024-00210-2'
            - Or 'url' (required): Full article URL
        
        For 'get_issue':
            - 'journal_id' (required): Journal numeric ID (e.g., '41290')
            - 'volume' (required): Volume number
            - 'issue' (required): Issue number
            - Or 'url' (required): Full issue page URL
        
        For 'list_issues':
            - 'journal_id' (required): Journal numeric ID
    
    Returns:
        Dict with 'success', 'data', and potentially 'error' keys.
    """
    function = params.get("function")
    if not function:
        return {"success": False, "error": "Missing required parameter: 'function'"}
    
    if function == "get_article":
        return await get_article(params, ctx)
    elif function == "get_issue":
        return await get_issue(params, ctx)
    elif function == "list_issues":
        return await list_issues(params, ctx)
    else:
        return {"success": False, "error": f"Unknown function: {function}"}


async def _fetch_html(session: aiohttp.ClientSession, url: str, headers: dict = None) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        default_headers.update(headers)
    
    async with session.get(url, headers=default_headers, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=True) as resp:
        html = await resp.text()
        return resp.status, html, str(resp.url)


def _extract_article_metadata(html: str, doi: str = None) -> dict[str, Any]:
    """Extract article metadata from HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    
    # Extract from JSON-LD
    json_ld = soup.find("script", type="application/ld+json")
    if json_ld:
        try:
            import json
            data = json.loads(json_ld.string)
            entity = data.get("mainEntity", {})
            
            result.update({
                "headline": entity.get("headline"),
                "description": entity.get("description"),
                "doi": entity.get("sameAs", "").replace("https://doi.org/", "") or doi,
                "date_published": entity.get("datePublished"),
                "date_modified": entity.get("dateModified"),
                "keywords": entity.get("keywords", []),
                "article_type": entity.get("@type"),
                "publisher": entity.get("publisher", {}).get("name"),
                "page_start": entity.get("pageStart"),
                "page_end": entity.get("pageEnd"),
            })
            
            # Journal info
            is_part_of = entity.get("isPartOf", {})
            result.update({
                "journal": is_part_of.get("name"),
                "issn": is_part_of.get("issn", []),
                "volume": is_part_of.get("volumeNumber"),
            })
            
            # Authors
            authors = entity.get("author", [])
            result["authors"] = [
                {
                    "name": a.get("name"),
                    "given_name": a.get("givenName"),
                    "family_name": a.get("familyName"),
                    "orcid": a.get("orcid"),
                    "affiliation": a.get("affiliation", {}).get("name") if isinstance(a.get("affiliation"), dict) else a.get("affiliation"),
                }
                for a in authors
            ]
            result["author_names"] = [a.get("name", "") for a in authors if a.get("name")]
            
        except Exception as e:
            result["json_ld_error"] = str(e)
    
    # Extract from citation meta tags (fallback/enrichment)
    citation_fields = {
        "citation_title": "citation_title",
        "citation_volume": "citation_volume",
        "citation_issue": "citation_issue",
        "citation_firstpage": "page_start",
        "citation_lastpage": "page_end",
        "citation_journal_title": "journal",
        "citation_doi": "doi",
        "citation_publisher": "publisher",
        "citation_issn": "issn_meta",
        "citation_language": "language",
        "citation_article_type": "article_type_meta",
        "citation_publication_date": "publication_date",
        "citation_online_date": "online_date",
        "citation_pdf_url": "pdf_url",
    }
    
    citation_meta = {}
    for meta_name, field in citation_fields.items():
        elements = soup.find_all("meta", attrs={"name": meta_name})
        if elements:
            values = [e.get("content", "") for e in elements if e.get("content")]
            if values:
                if len(values) == 1:
                    citation_meta[field] = values[0]
                else:
                    citation_meta[field] = values
    
    # Extract citation authors (can be multiple)
    author_elements = soup.find_all("meta", attrs={"name": "citation_author"})
    if author_elements:
        citation_meta["citation_authors"] = [a.get("content", "") for a in author_elements if a.get("content")]
    
    if citation_meta:
        result["citation_meta"] = citation_meta
        
        # Use citation meta to fill in missing fields
        if not result.get("headline") and citation_meta.get("citation_title"):
            result["headline"] = citation_meta["citation_title"]
        if not result.get("volume") and citation_meta.get("citation_volume"):
            result["volume"] = citation_meta["citation_volume"]
        if citation_meta.get("citation_issue"):
            result["issue"] = citation_meta["citation_issue"]
        if not result.get("doi") and citation_meta.get("doi"):
            result["doi"] = citation_meta["doi"]
        if citation_meta.get("pdf_url"):
            result["pdf_url"] = citation_meta["pdf_url"]
    
    # Extract abstract
    for meta_name in ["dc.description", "citation_abstract", "description"]:
        abstract_meta = soup.find("meta", attrs={"name": meta_name})
        if abstract_meta and abstract_meta.get("content"):
            result["abstract"] = abstract_meta.get("content")
            break
    
    # If no abstract in meta, try to find it in the page
    if not result.get("abstract"):
        abstract_section = soup.find(["div", "section", "p"], class_=re.compile(r"abstract|Abstract", re.I))
        if abstract_section:
            # Remove any nested headings
            for heading in abstract_section.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                heading.decompose()
            text = abstract_section.get_text(strip=True)
            if text and len(text) > 50:
                result["abstract"] = text[:2000]  # Limit length
    
    return result


def _extract_issue_articles(html: str, url: str = None) -> list[dict[str, Any]]:
    """Extract article listings from an issue page."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    
    # Find article items
    for article_elem in soup.find_all("article"):
        article_data = {}
        
        # Title and link
        title_link = article_elem.find("a", href=re.compile(r"/article/"))
        if title_link:
            article_data["title"] = title_link.get_text(strip=True)
            href = title_link.get("href", "")
            doi_match = re.search(r"/article/(10\.[\d.]+/[^\s?]+)", href)
            if doi_match:
                article_data["doi"] = doi_match.group(1)
                article_data["url"] = f"https://link.springer.com/article/{article_data['doi']}"
        
        # If no article link found, this might not be a real article
        if not article_data.get("doi"):
            continue
        
        # Authors - various patterns
        author_container = article_elem.find(["ul", "div", "p"], class_=re.compile(r"author|Author|creator", re.I))
        if author_container:
            author_links = author_container.find_all(["a", "span"])
            article_data["authors"] = [a.get_text(strip=True) for a in author_links if a.get_text(strip=True)]
        
        # Publication type/badge
        type_badge = article_elem.find(["span", "div"], class_=re.compile(r"type|badge|article-type", re.I))
        if type_badge:
            article_data["article_type"] = type_badge.get_text(strip=True)
        
        # Open access indicator
        oa_indicator = article_elem.find(["span", "div", "img"], class_=re.compile(r"open.?access|oa|free", re.I))
        if oa_indicator:
            article_data["open_access"] = True
        
        # Page info
        page_info = article_elem.find(string=re.compile(r"pp\.|pages|article\s+number", re.I))
        if page_info:
            article_data["page_info"] = page_info.strip()
        
        articles.append(article_data)
    
    return articles


def _extract_issue_info(html: str, url: str = None) -> dict[str, Any]:
    """Extract issue metadata from page."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    
    # Volume/issue from URL
    if url:
        match = re.search(r"/volumes-and-issues/(\d+)-(\d+)", url)
        if match:
            result["volume"] = match.group(1)
            result["issue"] = match.group(2)
    
    # Issue title
    issue_title = soup.find(["h1", "h2"], class_=re.compile(r"issue|Issue|volume|Volume", re.I))
    if issue_title:
        result["issue_title"] = issue_title.get_text(strip=True)
    
    # Journal title
    journal_header = soup.find(["h1", "a"], class_=re.compile(r"journal|Journal", re.I))
    if journal_header:
        result["journal"] = journal_header.get_text(strip=True)
    
    # From page title
    page_title = soup.find("title")
    if page_title:
        title_text = page_title.get_text(strip=True)
        if " | " in title_text:
            parts = title_text.split(" | ")
            if len(parts) >= 2:
                if not result.get("issue_title"):
                    result["issue_title"] = parts[0].strip()
                if not result.get("journal"):
                    result["journal"] = parts[1].strip()
    
    # ISSN
    issn_link = soup.find("a", href=re.compile(r"issn:"))
    if issn_link:
        result["issn"] = issn_link.get_text(strip=True)
    
    return result


def _extract_issues_list(html: str) -> list[dict[str, Any]]:
    """Extract list of issues from a journal issues page."""
    soup = BeautifulSoup(html, "html.parser")
    issues = []
    
    # Look for issue links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match patterns like /journal/12345/volumes-and-issues/12-4
        match = re.search(r"/journal/\d+/volumes-and-issues/(\d+)-(\d+)", href)
        if match:
            volume = match.group(1)
            issue_num = match.group(2)
            text = link.get_text(strip=True)
            
            issues.append({
                "volume": volume,
                "issue": issue_num,
                "label": text or f"Volume {volume}, Issue {issue_num}",
                "url": f"https://link.springer.com{href}" if href.startswith("/") else href,
            })
    
    # Deduplicate by volume+issue
    seen = set()
    unique_issues = []
    for issue in issues:
        key = f"{issue['volume']}-{issue['issue']}"
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)
    
    # Sort by volume (descending) then issue (descending)
    unique_issues.sort(key=lambda x: (int(x["volume"]), int(x["issue"])), reverse=True)
    
    return unique_issues


async def get_article(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract article metadata by DOI or URL.
    
    Args:
        params: Must contain 'doi' or 'url'
    
    Returns:
        Article metadata including title, authors, abstract, etc.
    """
    doi = params.get("doi")
    url = params.get("url")
    
    if not doi and not url:
        return {"success": False, "error": "Missing required parameter: 'doi' or 'url'"}
    
    if not url:
        # Normalize DOI
        doi = doi.strip()
        url = f"https://link.springer.com/article/{doi}"
    
    # Extract DOI from URL if not provided
    if not doi and url:
        match = re.search(r"/article/(10\.[\d.]+/[^\s?]+)", url)
        if match:
            doi = match.group(1)
    
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            status, html, final_url = await _fetch_html(session, url)
            
            if status == 404:
                return {
                    "success": False,
                    "error": "Article not found",
                    "error_code": "NOT_FOUND",
                    "doi": doi,
                    "url": url,
                }
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP error: {status}",
                    "error_code": "HTTP_ERROR",
                    "status_code": status,
                    "url": url,
                }
            
            # Check if we were redirected to an error page
            if "article" not in str(final_url).lower():
                # Might have been redirected elsewhere
                pass
            
            metadata = _extract_article_metadata(html, doi)
            
            if not metadata.get("headline") and not metadata.get("doi"):
                return {
                    "success": False,
                    "error": "Could not extract article metadata from page",
                    "error_code": "PARSE_ERROR",
                    "url": url,
                }
            
            return {
                "success": True,
                "data": {
                    "doi": metadata.get("doi") or doi,
                    "url": str(final_url),
                    "headline": metadata.get("headline"),
                    "authors": metadata.get("authors", []),
                    "author_names": metadata.get("author_names", []),
                    "journal": metadata.get("journal"),
                    "issn": metadata.get("issn"),
                    "volume": metadata.get("volume"),
                    "issue": metadata.get("issue"),
                    "page_start": metadata.get("page_start"),
                    "page_end": metadata.get("page_end"),
                    "date_published": metadata.get("date_published"),
                    "abstract": metadata.get("abstract"),
                    "keywords": metadata.get("keywords", []),
                    "publisher": metadata.get("publisher"),
                    "article_type": metadata.get("article_type"),
                    "pdf_url": metadata.get("pdf_url"),
                    "citation_meta": metadata.get("citation_meta"),
                },
            }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out",
            "error_code": "TIMEOUT",
            "url": url,
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR",
            "url": url,
        }


async def get_issue(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get article listings from a specific journal issue.
    
    Args:
        params: Requires either:
            - 'url' to the issue page, or
            - 'journal_id', 'volume', and 'issue'
    
    Returns:
        Issue metadata and list of articles.
    """
    url = params.get("url")
    journal_id = params.get("journal_id")
    volume = params.get("volume")
    issue = params.get("issue")
    
    if not url:
        if not all([journal_id, volume, issue]):
            return {
                "success": False,
                "error": "Missing required parameters: provide 'url' or 'journal_id', 'volume', and 'issue'"
            }
        url = f"https://link.springer.com/journal/{journal_id}/volumes-and-issues/{volume}-{issue}"
    
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            status, html, final_url = await _fetch_html(session, url)
            
            if status == 404:
                return {
                    "success": False,
                    "error": "Issue not found",
                    "error_code": "NOT_FOUND",
                    "url": url,
                }
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP error: {status}",
                    "error_code": "HTTP_ERROR",
                    "status_code": status,
                    "url": url,
                }
            
            issue_info = _extract_issue_info(html, str(final_url))
            articles = _extract_issue_articles(html, str(final_url))
            
            return {
                "success": True,
                "data": {
                    "url": str(final_url),
                    "volume": issue_info.get("volume") or volume,
                    "issue": issue_info.get("issue") or issue,
                    "issue_title": issue_info.get("issue_title"),
                    "journal": issue_info.get("journal"),
                    "issn": issue_info.get("issn"),
                    "article_count": len(articles),
                    "articles": articles,
                },
            }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out",
            "error_code": "TIMEOUT",
            "url": url,
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR",
            "url": url,
        }


async def list_issues(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List available issues for a journal.
    
    Args:
        params: Requires 'journal_id' and optionally 'volume' to filter
                or 'url' to a journal page
    
    Returns:
        List of available issues with URLs.
    """
    url = params.get("url")
    journal_id = params.get("journal_id")
    
    if not url and not journal_id:
        return {
            "success": False,
            "error": "Missing required parameter: 'journal_id' or 'url'"
        }
    
    if not url:
        # Try the volumes-and-issues page
        url = f"https://link.springer.com/journal/{journal_id}/volumes-and-issues"
    
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            status, html, final_url = await _fetch_html(session, url)
            
            if status == 404:
                return {
                    "success": False,
                    "error": "Journal not found",
                    "error_code": "NOT_FOUND",
                    "url": url,
                }
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP error: {status}",
                    "error_code": "HTTP_ERROR",
                    "status_code": status,
                    "url": url,
                }
            
            issues = _extract_issues_list(html)
            
            # Extract journal title
            soup = BeautifulSoup(html, "html.parser")
            journal_title = None
            title_elem = soup.find(["h1", "a"], class_=re.compile(r"journal|Journal", re.I))
            if title_elem:
                journal_title = title_elem.get_text(strip=True)
            
            return {
                "success": True,
                "data": {
                    "url": str(final_url),
                    "journal_id": journal_id,
                    "journal": journal_title,
                    "issue_count": len(issues),
                    "issues": issues[:50],  # Limit to 50
                },
            }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out",
            "error_code": "TIMEOUT",
            "url": url,
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "error_code": "NETWORK_ERROR",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "UNEXPECTED_ERROR",
            "url": url,
        }