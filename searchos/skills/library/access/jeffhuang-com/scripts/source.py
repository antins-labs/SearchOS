"""
Jeff Huang Best Paper Awards Scraper

Fetches best paper awards data from jeffhuang.com/best_paper_awards/
A comprehensive database of 1900+ best paper awards from top CS conferences (1996-2026).
"""

import aiohttp
import re
from typing import Any


async def _fetch_html(url: str) -> str:
    """Fetch HTML content from URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=60) as resp:
            resp.raise_for_status()
            return await resp.text()


def _parse_papers(html: str) -> list[dict]:
    """Parse all papers from the HTML content."""
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    
    papers = []
    current_year = None
    current_conf = None
    
    for table in tables:
        # Get year from thead
        thead_match = re.search(
            r'<thead[^>]*>.*?<th[^>]*>(\d{4})</th>.*?</thead>',
            table, re.DOTALL | re.IGNORECASE
        )
        if thead_match:
            current_year = thead_match.group(1)
            tbody_match = re.search(
                r'<tbody[^>]*>(.*?)</tbody>',
                table, re.DOTALL | re.IGNORECASE
            )
            if tbody_match:
                tbody = tbody_match.group(1)
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody, re.DOTALL | re.IGNORECASE)
                
                for row in rows:
                    # Check if this row has a conference header
                    conf_match = re.search(
                        r'<th[^>]*class="category-name"[^>]*>(.*?)</th>',
                        row, re.DOTALL | re.IGNORECASE
                    )
                    if conf_match:
                        conf_html = conf_match.group(1)
                        conf_abbr = re.search(r'<a[^>]*>([^<]+)</a>', conf_html)
                        conf_name = re.search(r'<span[^>]*>([^<]+)</span>', conf_html)
                        if conf_abbr:
                            current_conf = {
                                'abbr': conf_abbr.group(1).strip(),
                                'name': conf_name.group(1).strip() if conf_name else ''
                            }
                    
                    # Extract paper title and authors
                    td_matches = re.findall(
                        r'<td[^>]*>(.*?)</td>',
                        row, re.DOTALL | re.IGNORECASE
                    )
                    if len(td_matches) >= 2 and current_year and current_conf:
                        title_html = td_matches[0]
                        authors_html = td_matches[1]
                        
                        # Extract title
                        title = re.search(r'<a[^>]*>([^<]+)</a>', title_html)
                        title_text = title.group(1).strip() if title else re.sub(
                            r'<[^>]+>', '', title_html
                        ).strip()
                        
                        # Extract scholar link
                        scholar_link = re.search(
                            r'href="([^"]*scholar\.google\.com[^"]*)"',
                            title_html
                        )
                        scholar_url = scholar_link.group(1) if scholar_link else None
                        
                        # Extract ALL authors - expand hidden divs
                        hidden_divs = re.findall(
                            r'<div class="d-none">(.*?)</div>',
                            authors_html, re.DOTALL | re.IGNORECASE
                        )
                        
                        # Remove onclick links
                        authors_clean = re.sub(
                            r'<a[^>]*onclick[^>]*>.*?</a>',
                            '', authors_html, flags=re.DOTALL | re.IGNORECASE
                        )
                        
                        # Add hidden content
                        for hidden in hidden_divs:
                            authors_clean += '<br>' + hidden
                        
                        # Remove all tags and clean up
                        authors_clean = re.sub(r'<[^>]+>', '; ', authors_clean)
                        authors_clean = re.sub(r'\s*;\s*;\s*', '; ', authors_clean)
                        authors_clean = re.sub(r'^\s*;\s*', '', authors_clean)
                        authors_clean = re.sub(r'\s*;\s*$', '', authors_clean)
                        authors_clean = re.sub(r'\s+', ' ', authors_clean).strip()
                        
                        papers.append({
                            'year': current_year,
                            'conference': current_conf['abbr'],
                            'conference_name': current_conf['name'],
                            'title': title_text,
                            'authors': authors_clean,
                            'scholar_url': scholar_url
                        })
    
    return papers


async def get_all_papers(params: dict) -> dict:
    """Get all best paper awards data."""
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Apply pagination if specified
        limit = params.get('limit')
        offset = params.get('offset', 0)
        
        if offset > 0 or limit:
            papers = papers[offset:offset + limit] if limit else papers[offset:]
        
        return {
            'success': True,
            'count': len(papers),
            'papers': papers
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'papers': []
        }


async def get_papers_by_conference(params: dict) -> dict:
    """Get best paper awards for a specific conference."""
    conference = params.get('conference', '')
    if not conference:
        return {
            'success': False,
            'error': 'conference parameter is required',
            'papers': []
        }
    
    # Case-insensitive matching
    conference_normalized = conference.strip()
    
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Filter by conference (case-insensitive)
        filtered = [
            p for p in papers 
            if p['conference'].lower() == conference_normalized.lower()
        ]
        
        # Apply pagination
        limit = params.get('limit')
        offset = params.get('offset', 0)
        
        if offset > 0 or limit:
            filtered = filtered[offset:offset + limit] if limit else filtered[offset:]
        
        return {
            'success': True,
            'conference': conference,
            'count': len(filtered),
            'papers': filtered
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'papers': []
        }


async def get_papers_by_year(params: dict) -> dict:
    """Get best paper awards for a specific year."""
    year = params.get('year')
    if not year:
        return {
            'success': False,
            'error': 'year parameter is required',
            'papers': []
        }
    
    year = str(year)
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Filter by year
        filtered = [p for p in papers if p['year'] == year]
        
        # Apply pagination
        limit = params.get('limit')
        offset = params.get('offset', 0)
        
        if offset > 0 or limit:
            filtered = filtered[offset:offset + limit] if limit else filtered[offset:]
        
        return {
            'success': True,
            'year': year,
            'count': len(filtered),
            'papers': filtered
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'papers': []
        }


async def search_papers(params: dict) -> dict:
    """Search best paper awards by title or author keywords."""
    query = params.get('query', '').lower()
    search_in = params.get('search_in', 'all')  # 'title', 'authors', or 'all'
    
    if not query:
        return {
            'success': False,
            'error': 'query parameter is required',
            'papers': []
        }
    
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Filter by search query
        if search_in == 'title':
            filtered = [p for p in papers if query in p['title'].lower()]
        elif search_in == 'authors':
            filtered = [p for p in papers if query in p['authors'].lower()]
        else:  # all
            filtered = [
                p for p in papers 
                if query in p['title'].lower() or query in p['authors'].lower()
            ]
        
        # Apply pagination
        limit = params.get('limit')
        offset = params.get('offset', 0)
        
        if offset > 0 or limit:
            filtered = filtered[offset:offset + limit] if limit else filtered[offset:]
        
        return {
            'success': True,
            'query': query,
            'search_in': search_in,
            'count': len(filtered),
            'papers': filtered
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'papers': []
        }


async def get_statistics(params: dict) -> dict:
    """Get statistics about the best paper awards database."""
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Calculate statistics
        conferences = {}
        years = {}
        for p in papers:
            conf = p['conference']
            year = p['year']
            conferences[conf] = conferences.get(conf, 0) + 1
            years[year] = years.get(year, 0) + 1
        
        # Get conference details
        conf_details = {}
        for p in papers:
            conf = p['conference']
            if conf not in conf_details:
                conf_details[conf] = p['conference_name']
        
        return {
            'success': True,
            'total_papers': len(papers),
            'year_range': {
                'start': min(years.keys()),
                'end': max(years.keys())
            },
            'total_years': len(years),
            'total_conferences': len(conferences),
            'papers_per_conference': dict(sorted(conferences.items(), key=lambda x: -x[1])),
            'papers_per_year': dict(sorted(years.items())),
            'conference_details': conf_details
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def get_conferences(params: dict) -> dict:
    """Get list of all conferences in the database."""
    url = "https://jeffhuang.com/best_paper_awards/"
    
    try:
        html = await _fetch_html(url)
        papers = _parse_papers(html)
        
        # Extract unique conferences
        conferences = {}
        for p in papers:
            conf = p['conference']
            if conf not in conferences:
                conferences[conf] = {
                    'abbreviation': conf,
                    'full_name': p['conference_name'],
                    'paper_count': 0
                }
            conferences[conf]['paper_count'] += 1
        
        return {
            'success': True,
            'count': len(conferences),
            'conferences': list(sorted(conferences.values(), key=lambda x: -x['paper_count']))
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'conferences': []
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the skill function based on the 'function' parameter.
    
    Available functions:
    - get_all_papers: Get all best paper awards (with optional pagination)
    - get_papers_by_conference: Get papers for a specific conference
    - get_papers_by_year: Get papers for a specific year
    - search_papers: Search papers by title or author keywords
    - get_statistics: Get statistics about the database
    - get_conferences: Get list of all conferences
    """
    function = params.get('function', '')
    
    handlers = {
        'get_all_papers': get_all_papers,
        'get_papers_by_conference': get_papers_by_conference,
        'get_papers_by_year': get_papers_by_year,
        'search_papers': search_papers,
        'get_statistics': get_statistics,
        'get_conferences': get_conferences,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: {list(handlers.keys())}'
        }
    
    return await handler(params)