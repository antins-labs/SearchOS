"""
ACM Digital Library Access Skill

Fetches bibliographic metadata for ACM publications via Crossref and Semantic Scholar APIs.
The main dl.acm.org domain uses aggressive Cloudflare protection, so we use alternative
reliable APIs that provide the same structured data.

Supported functions:
- get_paper: Fetch metadata for a single paper by DOI
- search_papers: Search for papers by title/author keywords (via Semantic Scholar)
- get_citations: Get papers that cite a given DOI
- get_references: Get papers referenced by a given DOI
"""

import asyncio
import json
import re
from typing import Any
from playwright.async_api import async_playwright


async def fetch_json(url: str, timeout: int = 30000) -> dict:
    """Fetch JSON from a URL using Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            body = await page.query_selector('body')
            
            if not body:
                return {'error': 'No response body', 'url': url}
            
            text = await body.inner_text()
            
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                return {'error': f'JSON decode error: {e}', 'raw': text[:500]}
                
        except Exception as e:
            return {'error': str(e), 'url': url}
        finally:
            await browser.close()


def parse_doi(doi_input: str) -> str:
    """Parse and validate DOI from various input formats."""
    if not doi_input:
        return None
    
    doi_input = doi_input.strip()
    
    # If it's already a clean DOI (starts with 10.XXXX/)
    if re.match(r'^10\.\d{4,}/', doi_input):
        return doi_input
    
    # Extract from ACM DL URL: https://dl.acm.org/doi/10.1145/3641519.3657495
    acm_match = re.search(r'dl\.acm\.org/doi/(10\.\d{4,}/[^\s/?]+)', doi_input)
    if acm_match:
        return acm_match.group(1)
    
    # Extract from doi.org URL: https://doi.org/10.1145/3641519.3657495
    doi_org_match = re.search(r'doi\.org/(10\.\d{4,}/[^\s/?]+)', doi_input)
    if doi_org_match:
        return doi_org_match.group(1)
    
    # Extract from doi: prefix
    doi_prefix_match = re.search(r'doi:(10\.\d{4,}/[^\s]+)', doi_input, re.IGNORECASE)
    if doi_prefix_match:
        return doi_prefix_match.group(1)
    
    # If nothing matched but looks like it has a DOI pattern
    general_match = re.search(r'(10\.\d{4,}/[^\s]+)', doi_input)
    if general_match:
        return general_match.group(1)
    
    return None


async def get_crossref_data(doi: str) -> dict:
    """Fetch metadata from Crossref API."""
    url = f'https://api.crossref.org/works/{doi}'
    data = await fetch_json(url)
    
    if 'error' in data:
        return data
    
    msg = data.get('message', {})
    
    # Parse authors
    authors = []
    for author in msg.get('author', []):
        author_info = {
            'name': f"{author.get('given', '')} {author.get('family', '')}".strip(),
            'given': author.get('given', ''),
            'family': author.get('family', ''),
        }
        if author.get('affiliation'):
            author_info['affiliation'] = author['affiliation'][0].get('name', '')
        if author.get('ORCID'):
            author_info['orcid'] = author['ORCID']
        authors.append(author_info)
    
    # Parse publication date
    pub_date = msg.get('published-print') or msg.get('published-online') or msg.get('issued', {})
    date_parts = pub_date.get('date-parts', [[None]])
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    
    # Parse event/conference
    event = msg.get('event', {})
    
    result = {
        'doi': msg.get('DOI', doi),
        'title': msg.get('title', [''])[0] if msg.get('title') else None,
        'authors': authors,
        'author_count': len(authors),
        'year': year,
        'type': msg.get('type'),
        'publisher': msg.get('publisher'),
        'publisher_location': msg.get('publisher-location'),
        'container': msg.get('container-title', [None])[0] if msg.get('container-title') else None,
        'event': event.get('name') if event else None,
        'page': msg.get('page'),
        'url': msg.get('URL'),
        'license': msg.get('license', [{}])[0].get('URL') if msg.get('license') else None,
        'reference_count': msg.get('reference-count'),
        'citation_count': msg.get('is-referenced-by-count'),
        'funder': [f.get('name') for f in msg.get('funder', [])] if msg.get('funder') else None,
        'source': 'crossref',
    }
    
    # Remove None values
    return {k: v for k, v in result.items() if v is not None}


async def get_semantic_scholar_data(doi: str) -> dict:
    """Fetch metadata from Semantic Scholar API."""
    fields = 'title,authors,abstract,year,venue,citationCount,referenceCount,publicationVenue,externalIds,publicationDate,journal'
    url = f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={fields}'
    data = await fetch_json(url)
    
    if 'error' in data:
        return data
    
    # Check for API error
    if data.get('error'):
        return {'error': data.get('error'), 'code': data.get('code')}
    
    # Parse authors
    authors = []
    for author in data.get('authors', []):
        author_info = {
            'name': author.get('name'),
            'author_id': author.get('authorId'),
        }
        authors.append(author_info)
    
    pub_venue = data.get('publicationVenue', {})
    
    result = {
        'doi': doi,
        'title': data.get('title'),
        'abstract': data.get('abstract'),
        'authors': authors,
        'author_count': len(authors),
        'year': data.get('year'),
        'publication_date': data.get('publicationDate'),
        'venue': data.get('venue'),
        'publication_venue': pub_venue.get('name') if pub_venue else None,
        'venue_type': pub_venue.get('type') if pub_venue else None,
        'citation_count': data.get('citationCount'),
        'reference_count': data.get('referenceCount'),
        'semantic_scholar_id': data.get('paperId'),
        'external_ids': data.get('externalIds'),
        'source': 'semantic_scholar',
    }
    
    # Remove None values
    return {k: v for k, v in result.items() if v is not None}


async def merge_paper_data(crossref: dict, s2: dict) -> dict:
    """Merge data from Crossref and Semantic Scholar."""
    result = {
        'doi': crossref.get('doi') or s2.get('doi'),
        'title': crossref.get('title') or s2.get('title'),
        'abstract': s2.get('abstract'),  # Only S2 has abstracts
        'authors': crossref.get('authors') or s2.get('authors', []),
        'author_count': crossref.get('author_count') or s2.get('author_count'),
        'year': crossref.get('year') or s2.get('year'),
        'type': crossref.get('type'),
        'publisher': crossref.get('publisher'),
        'venue': s2.get('venue') or crossref.get('container'),
        'event': crossref.get('event'),
        'page': crossref.get('page'),
        'url': crossref.get('url') or f"https://doi.org/{crossref.get('doi') or s2.get('doi')}",
        'license': crossref.get('license'),
        'citation_count': s2.get('citation_count') or crossref.get('citation_count'),
        'reference_count': s2.get('reference_count') or crossref.get('reference_count'),
        'semantic_scholar_id': s2.get('semantic_scholar_id'),
        'sources': [],
    }
    
    if crossref and 'error' not in crossref:
        result['sources'].append('crossref')
    if s2 and 'error' not in s2:
        result['sources'].append('semantic_scholar')
    
    # Add affiliations from Crossref if available
    if crossref.get('authors'):
        result['authors'] = crossref['authors']
    
    # Remove None values
    return {k: v for k, v in result.items() if v is not None}


async def search_semantic_scholar(query: str, limit: int = 10) -> dict:
    """Search for papers on Semantic Scholar."""
    import urllib.parse
    encoded_query = urllib.parse.quote(query)
    fields = 'title,authors,year,venue,citationCount,abstract,externalIds,publicationVenue'
    url = f'https://api.semanticscholar.org/graph/v1/paper/search?query={encoded_query}&limit={limit}&fields={fields}'
    
    data = await fetch_json(url)
    
    if 'error' in data:
        return data
    
    papers = []
    for paper in data.get('data', []):
        authors = [a.get('name') for a in paper.get('authors', [])]
        
        paper_info = {
            'title': paper.get('title'),
            'authors': authors,
            'year': paper.get('year'),
            'venue': paper.get('venue'),
            'citation_count': paper.get('citationCount'),
            'doi': paper.get('externalIds', {}).get('DOI'),
            'semantic_scholar_id': paper.get('paperId'),
            'abstract': paper.get('abstract'),
        }
        papers.append({k: v for k, v in paper_info.items() if v is not None})
    
    return {
        'query': query,
        'total': data.get('total', len(papers)),
        'count': len(papers),
        'papers': papers,
    }


async def get_citations(doi: str, limit: int = 20) -> dict:
    """Get papers that cite the given DOI."""
    fields = 'title,authors,year,venue,citationCount,externalIds'
    url = f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/citations?fields={fields}&limit={limit}'
    
    data = await fetch_json(url)
    
    if 'error' in data:
        return data
    
    citations = []
    for item in data.get('data', []):
        paper = item.get('citingPaper', {})
        authors = [a.get('name') for a in paper.get('authors', [])]
        
        citation_info = {
            'title': paper.get('title'),
            'authors': authors,
            'year': paper.get('year'),
            'venue': paper.get('venue'),
            'citation_count': paper.get('citationCount'),
            'doi': paper.get('externalIds', {}).get('DOI'),
            'semantic_scholar_id': paper.get('paperId'),
        }
        citations.append({k: v for k, v in citation_info.items() if v is not None})
    
    return {
        'doi': doi,
        'total': data.get('total', len(citations)),
        'count': len(citations),
        'citations': citations,
    }


async def get_references(doi: str, limit: int = 20) -> dict:
    """Get papers referenced by the given DOI."""
    fields = 'title,authors,year,venue,citationCount,externalIds'
    url = f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/references?fields={fields}&limit={limit}'
    
    data = await fetch_json(url)
    
    if 'error' in data:
        return data
    
    references = []
    for item in data.get('data', []):
        paper = item.get('referencedPaper', {})
        if not paper:
            continue
            
        authors = [a.get('name') for a in paper.get('authors', [])]
        
        ref_info = {
            'title': paper.get('title'),
            'authors': authors,
            'year': paper.get('year'),
            'venue': paper.get('venue'),
            'citation_count': paper.get('citationCount'),
            'doi': paper.get('externalIds', {}).get('DOI'),
            'semantic_scholar_id': paper.get('paperId'),
        }
        references.append({k: v for k, v in ref_info.items() if v is not None})
    
    return {
        'doi': doi,
        'total': data.get('total', len(references)),
        'count': len(references),
        'references': references,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute ACM Digital Library access functions.
    
    Parameters:
        params: dict with keys:
            - function: str - one of 'get_paper', 'search_papers', 'get_citations', 'get_references'
            - doi: str (for get_paper, get_citations, get_references) - DOI or DOI URL
            - query: str (for search_papers) - search query
            - limit: int (optional) - max results for search/citations/references
    
    Returns:
        dict with requested data or error information
    """
    function = params.get('function', '')
    
    if function == 'get_paper':
        doi_input = params.get('doi', '')
        if not doi_input:
            return {'error': 'Missing required parameter: doi'}
        
        doi = parse_doi(doi_input)
        if not doi:
            return {'error': f'Invalid DOI format: {doi_input}'}
        
        # Fetch from both sources in parallel
        crossref_task = get_crossref_data(doi)
        s2_task = get_semantic_scholar_data(doi)
        
        crossref_data, s2_data = await asyncio.gather(crossref_task, s2_task)
        
        # Check if both failed
        if 'error' in crossref_data and 'error' in s2_data:
            return {
                'error': 'Failed to fetch data from both Crossref and Semantic Scholar',
                'crossref_error': crossref_data.get('error'),
                's2_error': s2_data.get('error'),
                'doi': doi,
            }
        
        # Merge the data
        result = await merge_paper_data(crossref_data, s2_data)
        return result
    
    elif function == 'search_papers':
        query = params.get('query', '')
        if not query:
            return {'error': 'Missing required parameter: query'}
        
        limit = params.get('limit', 10)
        return await search_semantic_scholar(query, limit)
    
    elif function == 'get_citations':
        doi_input = params.get('doi', '')
        if not doi_input:
            return {'error': 'Missing required parameter: doi'}
        
        doi = parse_doi(doi_input)
        if not doi:
            return {'error': f'Invalid DOI format: {doi_input}'}
        
        limit = params.get('limit', 20)
        return await get_citations(doi, limit)
    
    elif function == 'get_references':
        doi_input = params.get('doi', '')
        if not doi_input:
            return {'error': 'Missing required parameter: doi'}
        
        doi = parse_doi(doi_input)
        if not doi:
            return {'error': f'Invalid DOI format: {doi_input}'}
        
        limit = params.get('limit', 20)
        return await get_references(doi, limit)
    
    else:
        return {'error': f'Unknown function: {function}. Available functions: get_paper, search_papers, get_citations, get_references'}