"""
SearchOS access skill for GitHub Top-Conference-Best-Papers repository.

Extracts award-winning papers from top AI/ML conferences including:
ICLR, NeurIPS, ICML, CVPR, ICCV, ECCV, AAAI
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def _fetch_readme(url: str) -> str:
    """Fetch the GitHub page HTML."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.text()


def _parse_papers(html: str) -> list[dict]:
    """Parse all papers from the README markdown."""
    soup = BeautifulSoup(html, 'html.parser')
    readme = soup.find('article', class_='markdown-body')
    
    if not readme:
        return []
    
    papers = []
    current_conf = None
    current_category = None
    in_conferences_section = False
    
    for elem in readme.find_all(['h1', 'h2', 'h3', 'h4', 'ul']):
        text = elem.get_text(strip=True)
        
        # Skip the "Conferences Covered" section
        if elem.name == 'h2' and 'Conferences Covered' in text:
            in_conferences_section = True
            continue
        elif elem.name == 'h1' and 'Best Papers' in text:
            in_conferences_section = False
            continue
            
        if in_conferences_section:
            continue
        
        # Track current section headers
        if elem.name in ['h2', 'h3', 'h4']:
            if elem.name == 'h2':
                current_conf = text
                current_category = None
            else:
                current_category = text
        elif elem.name == 'ul':
            # Parse paper entries from list
            for li in elem.find_all('li', recursive=False):
                full_text = li.get_text(separator=' ', strip=True)
                links = li.find_all('a')
                
                if not links:
                    continue
                
                # Extract title - text before (CONF YEAR) pattern
                title_match = re.match(r'^(.+?)\s*\(([A-Z][A-Za-z]+\s+\d{4})\)', full_text)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    # Fallback: extract from full_text before [Paper]
                    title_extract = re.match(r'^(.+?)\s*\[', full_text)
                    if title_extract:
                        title = title_extract.group(1).strip()
                    else:
                        title = links[0].get_text(strip=True)
                
                # Extract venue and year from (CONF YEAR) pattern
                venue_match = re.search(r'\(([A-Z][A-Za-z]+)\s+(\d{4})\)', full_text)
                venue = venue_match.group(1).upper() if venue_match else None
                year = venue_match.group(2) if venue_match else None
                
                # Extract authors
                authors_match = re.search(r'Authors?:\s*(.+?)(?:\s*\[|$)', full_text)
                authors = authors_match.group(1).strip() if authors_match else None
                
                # Get paper URL - look for [Paper] link
                paper_link = None
                code_link = None
                for link in links:
                    href = link.get('href', '')
                    link_text = link.get_text(strip=True).lower()
                    if 'paper' in link_text:
                        paper_link = href
                    elif 'code' in link_text:
                        code_link = href
                
                # Fallback to first link if no [Paper] link
                if not paper_link and links:
                    paper_link = links[0].get('href', '')
                
                # Normalize URLs
                if paper_link and paper_link.startswith('/'):
                    paper_link = 'https://github.com' + paper_link
                if code_link and code_link.startswith('/'):
                    code_link = 'https://github.com' + code_link
                    
                papers.append({
                    'title': title,
                    'venue': venue,
                    'year': year,
                    'authors': authors,
                    'conference_section': current_conf,
                    'category': current_category,
                    'paper_url': paper_link,
                    'code_url': code_link,
                })
    
    return papers


def _filter_papers(papers: list[dict], filters: dict) -> list[dict]:
    """Filter papers by venue, year, category, etc."""
    result = papers
    
    if filters.get('venue'):
        venue_filter = filters['venue'].upper()
        result = [p for p in result if p.get('venue') == venue_filter]
    
    if filters.get('year'):
        year_filter = str(filters['year'])
        result = [p for p in result if p.get('year') == year_filter]
    
    if filters.get('category'):
        category_filter = filters['category'].lower()
        result = [p for p in result if p.get('category') and category_filter in p['category'].lower()]
    
    if filters.get('conference'):
        conf_filter = filters['conference'].upper()
        result = [p for p in result if p.get('conference_section') and conf_filter in p['conference_section'].upper()]
    
    if filters.get('title'):
        title_filter = filters['title'].lower()
        result = [p for p in result if title_filter in p.get('title', '').lower()]
    
    if filters.get('author'):
        author_filter = filters['author'].lower()
        result = [p for p in result if p.get('authors') and author_filter in p['authors'].lower()]
    
    return result


async def list_papers(params: dict) -> dict:
    """List all best papers with optional filtering."""
    url = "https://github.com/FeijiangHan/Top-Conference-Best-Papers"
    
    try:
        html = await _fetch_readme(url)
        papers = _parse_papers(html)
        
        # Apply filters
        filters = {
            'venue': params.get('venue'),
            'year': params.get('year'),
            'category': params.get('category'),
            'conference': params.get('conference'),
            'title': params.get('title'),
            'author': params.get('author'),
        }
        filtered = _filter_papers(papers, {k: v for k, v in filters.items() if v})
        
        # Limit results
        limit = params.get('limit', 50)
        limited = filtered[:limit]
        
        return {
            'success': True,
            'total': len(filtered),
            'returned': len(limited),
            'papers': limited,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_venues(params: dict) -> dict:
    """Get list of all venues and paper counts."""
    url = "https://github.com/FeijiangHan/Top-Conference-Best-Papers"
    
    try:
        html = await _fetch_readme(url)
        papers = _parse_papers(html)
        
        venue_counts = {}
        for p in papers:
            v = p.get('venue') or 'Unknown'
            venue_counts[v] = venue_counts.get(v, 0) + 1
        
        return {
            'success': True,
            'venues': dict(sorted(venue_counts.items(), key=lambda x: -x[1])),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_years(params: dict) -> dict:
    """Get list of all years and paper counts."""
    url = "https://github.com/FeijiangHan/Top-Conference-Best-Papers"
    
    try:
        html = await _fetch_readme(url)
        papers = _parse_papers(html)
        
        year_counts = {}
        for p in papers:
            y = p.get('year') or 'Unknown'
            year_counts[y] = year_counts.get(y, 0) + 1
        
        return {
            'success': True,
            'years': dict(sorted(year_counts.items())),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def get_categories(params: dict) -> dict:
    """Get list of all award categories and paper counts."""
    url = "https://github.com/FeijiangHan/Top-Conference-Best-Papers"
    
    try:
        html = await _fetch_readme(url)
        papers = _parse_papers(html)
        
        category_counts = {}
        for p in papers:
            c = p.get('category') or 'Unknown'
            category_counts[c] = category_counts.get(c, 0) + 1
        
        return {
            'success': True,
            'categories': dict(sorted(category_counts.items(), key=lambda x: -x[1])),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def search_papers(params: dict) -> dict:
    """Search papers by title or author keyword."""
    url = "https://github.com/FeijiangHan/Top-Conference-Best-Papers"
    
    try:
        html = await _fetch_readme(url)
        papers = _parse_papers(html)
        
        query = params.get('query', '').lower()
        if not query:
            return {'success': False, 'error': 'query parameter required'}
        
        # Search in title and authors
        results = []
        for p in papers:
            title = p.get('title', '').lower()
            authors = p.get('authors', '').lower()
            if query in title or query in authors:
                results.append(p)
        
        limit = params.get('limit', 20)
        limited = results[:limit]
        
        return {
            'success': True,
            'query': params.get('query'),
            'total': len(results),
            'returned': len(limited),
            'papers': limited,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on params['function']:
    - list_papers: List all best papers with optional filters
    - get_venues: Get list of venues (conferences) with paper counts
    - get_years: Get list of years with paper counts
    - get_categories: Get list of award categories with paper counts
    - search_papers: Search papers by title or author keyword
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required. Available functions: list_papers, get_venues, get_years, get_categories, search_papers'
        }
    
    handlers = {
        'list_papers': list_papers,
        'get_venues': get_venues,
        'get_years': get_years,
        'get_categories': get_categories,
        'search_papers': search_papers,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: {list(handlers.keys())}'
        }
    
    return await handler(params)