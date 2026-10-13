"""
PaperCopilot Access Skill - Extract paper lists from papercopilot.com
"""

import asyncio
import aiohttp
import re
from typing import Any


async def _fetch_papers(
    session: aiohttp.ClientSession,
    conf: str,
    year: str,
    track: str = "main",
    batch: int = 0,
    filters: list = None,
) -> dict:
    """Fetch a batch of papers from the PaperCopilot API."""
    base_url = "https://papercopilot.com/wp-admin/admin-ajax.php"
    
    params = {
        'action': 'load_paperlist',
        'batch': str(batch),
        'conf': conf.lower(),
        'year': str(year),
        'mode': 'detail',
        'track': track,
        'surface': 'papers',
        'filters': '[]' if filters is None else str(filters),
        'paper_dims': '["abstract","keywords","rating_avg"]'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://papercopilot.com/paper-list/{conf}-paper-list/{conf}-{year}-paper-list/',
        'Accept': 'application/json',
    }
    
    async with session.get(base_url, params=params, headers=headers, timeout=30) as resp:
        if resp.status != 200:
            return {'error': f'HTTP {resp.status}', 'papers': []}
        
        try:
            data = await resp.json()
        except Exception as e:
            return {'error': f'JSON parse error: {e}', 'papers': []}
        
        if 'html' not in data:
            return {'error': 'No HTML in response', 'papers': []}
        
        html = data.get('html', '')
        if not html:
            return {'papers': [], 'batch': batch, 'total_in_batch': 0}
        
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        papers = []
        
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) < 4:
                continue
            
            # Extract number
            num = re.sub(r'<[^>]+>', '', cells[0]).strip()
            
            # Extract title and URL
            title_cell = cells[1]
            link_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', title_cell, re.DOTALL)
            if link_match:
                title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
                url = link_match.group(1)
            else:
                # No link - extract title from text before <br>
                title = re.sub(r'<br.*', '', title_cell, flags=re.DOTALL)
                title = re.sub(r'<[^>]+>', '', title).strip()
                url = ''
            
            # Extract session/area
            session_area = re.sub(r'<[^>]+>', '', cells[2]).strip()
            
            # Extract status
            status = re.sub(r'<[^>]+>', '', cells[3]).strip()
            
            # Extract abstract if available (cell 4)
            abstract = ''
            if len(cells) > 4:
                abstract_match = re.search(r'data-search="([^"]*)"', cells[4])
                if abstract_match:
                    abstract = abstract_match.group(1)
            
            papers.append({
                'number': int(num) if num.isdigit() else num,
                'title': title,
                'url': url,
                'session': session_area,
                'status': status,
                'abstract': abstract[:500] if abstract else '',
            })
        
        return {'papers': papers, 'batch': batch}


async def _fetch_all_papers(
    conf: str,
    year: str,
    track: str = "main",
    max_batches: int = 100,  # Increased for large conferences like ICLR
) -> dict:
    """Fetch all papers by iterating through batches."""
    all_papers = []
    
    async with aiohttp.ClientSession() as session:
        for batch in range(max_batches):
            result = await _fetch_papers(session, conf, year, track, batch)
            
            if 'error' in result and result.get('error'):
                # If first batch fails, return error
                if batch == 0:
                    return result
                # Otherwise, stop fetching
                break
            
            papers = result.get('papers', [])
            if not papers:
                break
            
            all_papers.extend(papers)
            
            # If we got fewer than 100 papers, we've reached the end
            if len(papers) < 100:
                break
    
    return {
        'papers': all_papers,
        'total': len(all_papers),
        'conference': conf.upper(),
        'year': year,
    }


async def _get_paper_by_title(
    conf: str,
    year: str,
    title_query: str,
    track: str = "main",
) -> dict:
    """Search for a specific paper by title."""
    result = await _fetch_all_papers(conf, year, track)
    
    if 'error' in result:
        return result
    
    papers = result.get('papers', [])
    title_lower = title_query.lower()
    
    matches = [
        p for p in papers
        if title_lower in p.get('title', '').lower()
    ]
    
    return {
        'papers': matches,
        'total': len(matches),
        'query': title_query,
        'conference': conf.upper(),
        'year': year,
    }


async def _get_papers_by_session(
    conf: str,
    year: str,
    session_query: str,
    track: str = "main",
) -> dict:
    """Get papers filtered by session/area."""
    result = await _fetch_all_papers(conf, year, track)
    
    if 'error' in result:
        return result
    
    papers = result.get('papers', [])
    session_lower = session_query.lower()
    
    matches = [
        p for p in papers
        if session_lower in p.get('session', '').lower()
    ]
    
    return {
        'papers': matches,
        'total': len(matches),
        'session_filter': session_query,
        'conference': conf.upper(),
        'year': year,
    }


async def _get_papers_by_status(
    conf: str,
    year: str,
    status_query: str,
    track: str = "main",
) -> dict:
    """Get papers filtered by status (e.g., Technical Paper, Poster)."""
    result = await _fetch_all_papers(conf, year, track)
    
    if 'error' in result:
        return result
    
    papers = result.get('papers', [])
    status_lower = status_query.lower()
    
    matches = [
        p for p in papers
        if status_lower in p.get('status', '').lower()
    ]
    
    return {
        'papers': matches,
        'total': len(matches),
        'status_filter': status_query,
        'conference': conf.upper(),
        'year': year,
    }


async def _list_available_conferences() -> dict:
    """Return list of known conferences on PaperCopilot."""
    return {
        'conferences': [
            {'id': 'siggraph', 'name': 'SIGGRAPH', 'years': [2022, 2023, 2024]},
            {'id': 'cvpr', 'name': 'CVPR', 'years': list(range(2013, 2026))},
            {'id': 'iccv', 'name': 'ICCV', 'years': [2013, 2015, 2017, 2019, 2021, 2023, 2025]},
            {'id': 'eccv', 'name': 'ECCV', 'years': [2018, 2020, 2022, 2024]},
            {'id': 'iclr', 'name': 'ICLR', 'years': list(range(2013, 2026))},
            {'id': 'neurips', 'name': 'NeurIPS', 'years': [2020, 2021, 2022, 2023]},
            {'id': 'icml', 'name': 'ICML', 'years': list(range(2020, 2025))},
            {'id': 'aaai', 'name': 'AAAI', 'years': list(range(2021, 2026))},
            {'id': 'acl', 'name': 'ACL', 'years': list(range(2021, 2026))},
            {'id': 'emnlp', 'name': 'EMNLP', 'years': list(range(2021, 2025))},
        ],
        'note': 'This is a partial list. Visit papercopilot.com for the full list of supported conferences.'
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute PaperCopilot skill.
    
    Functions:
    - list_papers: Get all papers for a conference/year
    - search_paper: Search for papers by title
    - filter_by_session: Get papers by session/area
    - filter_by_status: Get papers by status type
    - list_conferences: List available conferences
    """
    function = params.get('function', '')
    
    if function == 'list_papers':
        conf = params.get('conference', '')
        year = params.get('year', '')
        track = params.get('track', 'main')
        
        if not conf or not year:
            return {
                'error': 'Missing required parameters: conference and year',
                'papers': [],
            }
        
        return await _fetch_all_papers(conf, year, track)
    
    elif function == 'search_paper':
        conf = params.get('conference', '')
        year = params.get('year', '')
        title = params.get('title', '')
        track = params.get('track', 'main')
        
        if not conf or not year or not title:
            return {
                'error': 'Missing required parameters: conference, year, and title',
                'papers': [],
            }
        
        return await _get_paper_by_title(conf, year, title, track)
    
    elif function == 'filter_by_session':
        conf = params.get('conference', '')
        year = params.get('year', '')
        session = params.get('session', '')
        track = params.get('track', 'main')
        
        if not conf or not year or not session:
            return {
                'error': 'Missing required parameters: conference, year, and session',
                'papers': [],
            }
        
        return await _get_papers_by_session(conf, year, session, track)
    
    elif function == 'filter_by_status':
        conf = params.get('conference', '')
        year = params.get('year', '')
        status = params.get('status', '')
        track = params.get('track', 'main')
        
        if not conf or not year or not status:
            return {
                'error': 'Missing required parameters: conference, year, and status',
                'papers': [],
            }
        
        return await _get_papers_by_status(conf, year, status, track)
    
    elif function == 'list_conferences':
        return await _list_available_conferences()
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'list_papers',
                'search_paper',
                'filter_by_session',
                'filter_by_status',
                'list_conferences'
            ]
        }