"""
Wiley Online Library Access Skill

Fetches journal article metadata from Wiley-hosted content using alternative
API sources (CrossRef, Semantic Scholar) to bypass Cloudflare protection.

The direct Wiley site (onlinelibrary.wiley.com) is protected by Cloudflare
and returns 403 errors for automated access. This skill uses public APIs
that index Wiley content to retrieve comprehensive article metadata.
"""

import asyncio
import re
from typing import Any
import aiohttp
from html import unescape


async def fetch_crossref(doi: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Fetch article metadata from CrossRef API.
    
    CrossRef provides comprehensive bibliographic metadata including:
    - Title, authors, journal, volume, issue, pages
    - Publication dates, ISSN, abstract
    - Citation count, license info, links
    """
    url = f"https://api.crossref.org/works/{doi}"
    headers = {
        'User-Agent': 'SearchOS/1.0 (mailto:searchos@example.com)',
        'Accept': 'application/json'
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {'success': True, 'data': data.get('message', {})}
            else:
                text = await resp.text()
                return {'success': False, 'error': f'CrossRef HTTP {resp.status}: {text[:200]}'}
    except asyncio.TimeoutError:
        return {'success': False, 'error': 'CrossRef request timed out'}
    except Exception as e:
        return {'success': False, 'error': f'CrossRef error: {str(e)}'}


async def fetch_semantic_scholar(doi: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Fetch article metadata from Semantic Scholar API.
    
    Semantic Scholar provides:
    - Citation count, reference count
    - Clean abstract (without HTML tags)
    - Open access PDF availability
    - Fields of study, publication types
    - Author IDs for further research
    """
    fields = "title,abstract,year,authors,journal,openAccessPdf,citationCount,referenceCount,url,publicationDate,publicationTypes,externalIds,fieldsOfStudy,s2FieldsOfStudy,venue,isOpenAccess"
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={fields}"
    headers = {
        'User-Agent': 'SearchOS/1.0 (mailto:searchos@example.com)',
        'Accept': 'application/json'
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {'success': True, 'data': data}
            elif resp.status == 404:
                return {'success': False, 'error': 'Semantic Scholar: DOI not found'}
            else:
                text = await resp.text()
                return {'success': False, 'error': f'Semantic Scholar HTTP {resp.status}: {text[:200]}'}
    except asyncio.TimeoutError:
        return {'success': False, 'error': 'Semantic Scholar request timed out'}
    except Exception as e:
        return {'success': False, 'error': f'Semantic Scholar error: {str(e)}'}


def parse_crossref_date(date_obj: dict | None) -> str | None:
    """Parse CrossRef date-parts into ISO date string."""
    if not date_obj:
        return None
    date_parts = date_obj.get('date-parts', [[]])
    if date_parts and date_parts[0]:
        parts = date_parts[0]
        if len(parts) >= 3:
            return f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
        elif len(parts) >= 2:
            return f"{parts[0]}-{parts[1]:02d}"
        elif len(parts) >= 1:
            return str(parts[0])
    return None


def clean_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ''
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def normalize_crossref(data: dict) -> dict[str, Any]:
    """Normalize CrossRef data to standard format."""
    result = {
        'source': 'crossref',
        'doi': data.get('DOI'),
        'title': None,
        'authors': [],
        'journal': None,
        'journal_short': None,
        'year': None,
        'volume': data.get('volume'),
        'issue': data.get('issue'),
        'pages': data.get('page'),
        'abstract': None,
        'type': data.get('type'),
        'publisher': data.get('publisher'),
        'issn': [],
        'url': data.get('URL'),
        'license': [],
        'citation_count': data.get('is-referenced-by-count'),
        'reference_count': data.get('references-count'),
        'published_date': None,
        'created_date': None,
        'subjects': [],
    }
    
    # Title
    titles = data.get('title', [])
    if titles:
        result['title'] = titles[0]
    
    # Authors
    authors = data.get('author', [])
    for author in authors:
        author_info = {
            'given': author.get('given'),
            'family': author.get('family'),
            'name': f"{author.get('given', '')} {author.get('family', '')}".strip(),
            'orcid': author.get('ORCID'),
            'affiliation': [a.get('name') for a in author.get('affiliation', []) if a.get('name')],
        }
        result['authors'].append(author_info)
    
    # Journal
    container = data.get('container-title', [])
    if container:
        result['journal'] = container[0]
    
    short_container = data.get('short-container-title', [])
    if short_container:
        result['journal_short'] = short_container[0]
    
    # Year from various date fields
    for date_field in ['published-print', 'published-online', 'published', 'issued']:
        date_str = parse_crossref_date(data.get(date_field))
        if date_str:
            result['published_date'] = date_str
            result['year'] = int(date_str.split('-')[0])
            break
    
    # Created date
    result['created_date'] = parse_crossref_date(data.get('created'))
    
    # Abstract (clean HTML)
    abstract = data.get('abstract')
    if abstract:
        result['abstract'] = clean_html(abstract)
    
    # ISSN
    issn_list = data.get('ISSN', [])
    result['issn'] = issn_list if issn_list else []
    
    # Subjects
    subjects = data.get('subject', [])
    result['subjects'] = subjects if subjects else []
    
    # Licenses
    licenses = data.get('license', [])
    for lic in licenses:
        result['license'].append({
            'url': lic.get('URL'),
            'content_version': lic.get('content-version'),
            'start_date': parse_crossref_date(lic.get('start')),
        })
    
    return result


def normalize_semantic_scholar(data: dict) -> dict[str, Any]:
    """Normalize Semantic Scholar data to standard format."""
    result = {
        'source': 'semanticscholar',
        'doi': None,
        'semantic_scholar_id': data.get('paperId'),
        'title': data.get('title'),
        'authors': [],
        'journal': None,
        'venue': data.get('venue'),
        'year': data.get('year'),
        'publication_date': data.get('publicationDate'),
        'abstract': data.get('abstract'),
        'citation_count': data.get('citationCount'),
        'reference_count': data.get('referenceCount'),
        'open_access': None,
        'fields_of_study': [],
        'publication_types': data.get('publicationTypes', []),
        'url': data.get('url'),
    }
    
    # DOI from external IDs
    ext_ids = data.get('externalIds', {})
    result['doi'] = ext_ids.get('DOI')
    
    # Authors
    authors = data.get('authors', [])
    for author in authors:
        result['authors'].append({
            'name': author.get('name'),
            'author_id': author.get('authorId'),
        })
    
    # Journal
    journal = data.get('journal', {})
    if journal:
        result['journal'] = journal.get('name')
    
    # Open access info
    oa = data.get('openAccessPdf', {})
    if oa:
        result['open_access'] = {
            'is_open_access': data.get('isOpenAccess', False),
            'pdf_url': oa.get('url') if oa.get('url') else None,
        }
    
    # Fields of study
    s2_fields = data.get('s2FieldsOfStudy', [])
    for field in s2_fields:
        result['fields_of_study'].append({
            'category': field.get('category'),
            'source': field.get('source'),
        })
    
    return result


def merge_metadata(crossref: dict | None, s2: dict | None) -> dict[str, Any]:
    """Merge metadata from multiple sources, preferring CrossRef for bibliography."""
    merged = {
        'doi': None,
        'title': None,
        'authors': [],
        'abstract': None,
        'journal': None,
        'journal_short': None,
        'year': None,
        'volume': None,
        'issue': None,
        'pages': None,
        'publisher': None,
        'type': None,
        'issn': [],
        'citation_count': None,
        'reference_count': None,
        'open_access': None,
        'fields_of_study': [],
        'subjects': [],
        'urls': {},
        'sources': [],
        'license': [],
    }
    
    # Start with CrossRef (more authoritative for bibliography)
    if crossref:
        merged['doi'] = crossref.get('doi')
        merged['title'] = crossref.get('title')
        merged['authors'] = crossref.get('authors', [])
        merged['abstract'] = crossref.get('abstract')
        merged['journal'] = crossref.get('journal')
        merged['journal_short'] = crossref.get('journal_short')
        merged['year'] = crossref.get('year')
        merged['volume'] = crossref.get('volume')
        merged['issue'] = crossref.get('issue')
        merged['pages'] = crossref.get('pages')
        merged['publisher'] = crossref.get('publisher')
        merged['type'] = crossref.get('type')
        merged['issn'] = crossref.get('issn', [])
        merged['citation_count'] = crossref.get('citation_count')
        merged['reference_count'] = crossref.get('reference_count')
        merged['subjects'] = crossref.get('subjects', [])
        merged['license'] = crossref.get('license', [])
        merged['urls']['crossref'] = crossref.get('url')
        merged['published_date'] = crossref.get('published_date')
        merged['sources'].append('crossref')
    
    # Enhance with Semantic Scholar data
    if s2:
        # Use S2 abstract if CrossRef doesn't have one
        if not merged['abstract'] and s2.get('abstract'):
            merged['abstract'] = s2.get('abstract')
        
        # Use S2 citation count if CrossRef doesn't have one
        if merged['citation_count'] is None and s2.get('citation_count') is not None:
            merged['citation_count'] = s2.get('citation_count')
        
        # Add open access info
        if s2.get('open_access'):
            merged['open_access'] = s2.get('open_access')
        
        # Add fields of study
        if s2.get('fields_of_study'):
            merged['fields_of_study'] = s2.get('fields_of_study', [])
        
        # Add Semantic Scholar URL
        merged['urls']['semanticscholar'] = s2.get('url')
        merged['semantic_scholar_id'] = s2.get('semantic_scholar_id')
        merged['sources'].append('semanticscholar')
    
    return merged


async def fetch_article(doi: str) -> dict[str, Any]:
    """
    Fetch article metadata from all available sources.
    
    Args:
        doi: The DOI of the article (e.g., "10.1111/ajes.12597")
    
    Returns:
        Dict with merged article metadata from CrossRef and Semantic Scholar.
    """
    # Normalize DOI (remove URL prefix if present)
    doi = doi.strip()
    if doi.startswith('https://doi.org/'):
        doi = doi.replace('https://doi.org/', '')
    elif doi.startswith('http://doi.org/'):
        doi = doi.replace('http://doi.org/', '')
    elif doi.startswith('https://onlinelibrary.wiley.com/doi/'):
        # Handle Wiley URLs
        match = re.search(r'/doi/(?:abs/)?([\d.]+/[^\s/]+)', doi)
        if match:
            doi = match.group(1)
    
    async with aiohttp.ClientSession() as session:
        # Fetch from both sources in parallel
        crossref_task = fetch_crossref(doi, session)
        s2_task = fetch_semantic_scholar(doi, session)
        
        crossref_result, s2_result = await asyncio.gather(crossref_task, s2_task)
        
    errors = []
    crossref_data = None
    s2_data = None
    
    if crossref_result['success']:
        crossref_data = normalize_crossref(crossref_result['data'])
    else:
        errors.append(crossref_result['error'])
    
    if s2_result['success']:
        s2_data = normalize_semantic_scholar(s2_result['data'])
    else:
        errors.append(s2_result['error'])
    
    if not crossref_data and not s2_data:
        return {
            'success': False,
            'error': 'Failed to fetch metadata from any source',
            'details': errors,
            'doi': doi,
        }
    
    merged = merge_metadata(crossref_data, s2_data)
    
    return {
        'success': True,
        'data': merged,
        'doi': doi,
        'sources_used': merged['sources'],
        'warnings': errors if errors else None,
    }


async def fetch_articles(dois: list[str]) -> dict[str, Any]:
    """
    Fetch metadata for multiple articles.
    
    Args:
        dois: List of DOI strings
    
    Returns:
        Dict with list of article metadata and summary statistics.
    """
    results = []
    errors = []
    
    for doi in dois:
        result = await fetch_article(doi)
        results.append(result)
        if not result.get('success'):
            errors.append({'doi': doi, 'error': result.get('error')})
    
    successful = [r for r in results if r.get('success')]
    
    return {
        'success': len(successful) > 0,
        'articles': results,
        'summary': {
            'total': len(dois),
            'successful': len(successful),
            'failed': len(errors),
        },
        'errors': errors if errors else None,
    }


def extract_doi_from_url(url: str) -> str | None:
    """Extract DOI from various URL formats."""
    # Direct DOI
    if re.match(r'^10\.\d{4,}/[^\s]+$', url):
        return url
    
    # doi.org URL
    match = re.search(r'doi\.org/(10\.[^\s/]+/[^\s]+)', url)
    if match:
        return match.group(1)
    
    # Wiley Online Library URL
    match = re.search(r'onlinelibrary\.wiley\.com/doi/(?:abs/|full/|pdf/)?(10\.[^\s/]+/[^\s/?]+)', url)
    if match:
        return match.group(1)
    
    return None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Wiley Online Library access skill.
    
    Functions:
        - fetch_article: Fetch metadata for a single article by DOI or Wiley URL
        - fetch_articles: Fetch metadata for multiple articles by DOI
        - extract_doi: Extract DOI from a Wiley or doi.org URL
    
    Args:
        params: Dict containing:
            - function: One of 'fetch_article', 'fetch_articles', 'extract_doi'
            - doi: DOI string (for fetch_article)
            - dois: List of DOI strings (for fetch_articles)
            - url: URL to extract DOI from (for extract_doi)
    
    Returns:
        Dict with success status and data/error information.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'available_functions': ['fetch_article', 'fetch_articles', 'extract_doi'],
        }
    
    if function == 'fetch_article':
        doi = params.get('doi') or params.get('url')
        if not doi:
            return {
                'success': False,
                'error': 'Missing required parameter: doi or url',
            }
        return await fetch_article(doi)
    
    elif function == 'fetch_articles':
        dois = params.get('dois')
        if not dois:
            return {
                'success': False,
                'error': 'Missing required parameter: dois',
            }
        if isinstance(dois, str):
            # Allow comma or newline separated string
            dois = [d.strip() for d in dois.replace('\n', ',').split(',') if d.strip()]
        return await fetch_articles(dois)
    
    elif function == 'extract_doi':
        url = params.get('url')
        if not url:
            return {
                'success': False,
                'error': 'Missing required parameter: url',
            }
        doi = extract_doi_from_url(url)
        if doi:
            return {
                'success': True,
                'doi': doi,
                'url': url,
            }
        else:
            return {
                'success': False,
                'error': 'Could not extract DOI from URL',
                'url': url,
            }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': ['fetch_article', 'fetch_articles', 'extract_doi'],
        }