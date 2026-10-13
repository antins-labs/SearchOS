"""
StatMuse Football Statistics Access Skill

Fetches statistical query results from StatMuse FC (football) section.
Parses HTML tables from statmuse.com/fc/ask pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional
import html


async def fetch_page(session: aiohttp.ClientSession, query: str) -> tuple[int, str]:
    """Fetch the StatMuse page for a given query.
    
    Args:
        session: aiohttp client session
        query: Search query string
        
    Returns:
        Tuple of (status_code, html_content)
    """
    url = f"https://www.statmuse.com/fc/ask?q={query.replace(' ', '+')}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with session.get(url, headers=headers) as response:
        html_content = await response.text()
        return response.status, html_content


def parse_tables(html_content: str) -> Dict[str, Any]:
    """Parse all tables from HTML content.
    
    Args:
        html_content: Raw HTML from StatMuse page
        
    Returns:
        Dictionary with tables data or error
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Check for error message (query not understood)
    h1 = soup.find('h1')
    if h1 and "didn't understand" in h1.get_text().lower():
        return {
            'error': 'query_not_understood',
            'message': 'StatMuse did not understand the query. Try rephrasing your question. Examples that work: "premier league top scorers 2023-24", "highest rated la liga players", "real madrid vs barcelona"',
            'tables': []
        }
    
    tables = soup.find_all('table')
    
    if not tables:
        return {
            'error': 'no_data',
            'message': 'No data tables found for this query.',
            'tables': []
        }
    
    parsed_tables = []
    
    for idx, table in enumerate(tables):
        # Get headers
        headers = []
        thead = table.find('thead')
        if thead:
            for th in thead.find_all('th'):
                header_text = th.get_text(strip=True)
                headers.append(header_text)
        
        # Get rows
        tbody = table.find('tbody') or table
        all_rows = tbody.find_all('tr')
        
        # Filter to only data rows (rows with td elements)
        data_rows = []
        for row in all_rows:
            cells = row.find_all(['td', 'th'])
            if cells:
                cell_data = [cell.get_text(strip=True) for cell in cells]
                data_rows.append(cell_data)
        
        if headers or data_rows:
            parsed_tables.append({
                'index': idx,
                'headers': headers,
                'rows': data_rows,
                'row_count': len(data_rows)
            })
    
    return {
        'error': None,
        'tables': parsed_tables,
        'table_count': len(parsed_tables)
    }


def format_table_as_text(table: Dict[str, Any], max_rows: Optional[int] = None) -> str:
    """Format a single table as readable text.
    
    Args:
        table: Parsed table dictionary
        max_rows: Maximum number of rows to include (None for all)
        
    Returns:
        Formatted text representation
    """
    lines = []
    
    headers = table.get('headers', [])
    rows = table.get('rows', [])
    
    if max_rows:
        rows = rows[:max_rows]
    
    if headers:
        lines.append(' | '.join(headers))
        lines.append('-' * len(' | '.join(headers)))
    
    for row in rows:
        lines.append(' | '.join(row))
    
    return '\n'.join(lines)


async def ask(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Query StatMuse FC with a natural language question.
    
    Args:
        params: Dictionary containing:
            - query: Natural language query string
            - format: (optional) 'full', 'first_table', 'text' - default 'first_table'
            
    Returns:
        Dictionary with parsed table data
    """
    query = params.get('query', '').strip()
    output_format = params.get('format', 'first_table')
    
    if not query:
        return {
            'error': 'missing_query',
            'message': 'Query parameter is required'
        }
    
    async with aiohttp.ClientSession() as session:
        status, html_content = await fetch_page(session, query)
        
        # Handle HTTP 422 (Unprocessable Entity) - StatMuse returns this for queries it doesn't understand
        if status == 422:
            return {
                'error': 'query_not_understood',
                'message': 'StatMuse did not understand the query. Try rephrasing your question. Examples that work: "premier league top scorers 2023-24", "highest rated la liga players", "real madrid vs barcelona"'
            }
        
        if status != 200:
            return {
                'error': 'http_error',
                'message': f'HTTP error {status}',
                'status_code': status
            }
        
        result = parse_tables(html_content)
        
        if result.get('error'):
            return result
        
        tables = result.get('tables', [])
        
        if output_format == 'full':
            return {
                'error': None,
                'query': query,
                'table_count': len(tables),
                'tables': tables
            }
        
        elif output_format == 'text':
            # Return formatted text of all tables
            text_parts = []
            for table in tables:
                text_parts.append(format_table_as_text(table))
                text_parts.append('')  # Empty line between tables
            
            return {
                'error': None,
                'query': query,
                'text': '\n'.join(text_parts).strip(),
                'table_count': len(tables)
            }
        
        else:  # 'first_table' - default
            if not tables:
                return {
                    'error': 'no_data',
                    'message': 'No data tables found',
                    'query': query
                }
            
            first_table = tables[0]
            return {
                'error': None,
                'query': query,
                'headers': first_table['headers'],
                'rows': first_table['rows'],
                'row_count': first_table['row_count'],
                'text': format_table_as_text(first_table),
                'other_tables_count': len(tables) - 1
            }


async def search_player_stats(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Search for player statistics with structured parameters.
    
    Args:
        params: Dictionary containing:
            - player: Player name (optional)
            - season: Season string like '2023-24' (optional)
            - league: League name like 'premier league', 'la liga' (optional)
            - stat: Stat to sort by like 'goals', 'assists', 'rating' (optional)
            - club: Club/team name (optional)
            - limit: Max results (default 25)
            
    Returns:
        Dictionary with player statistics table
    """
    player = params.get('player', '').strip()
    season = params.get('season', '').strip()
    league = params.get('league', '').strip()
    stat = params.get('stat', '').strip()
    club = params.get('club', '').strip()
    limit = params.get('limit', 25)
    
    # Build query from parameters
    query_parts = []
    
    if stat:
        # Map common stat names to StatMuse query patterns
        stat_mapping = {
            'goals': 'top scorers',
            'scorers': 'top scorers',
            'assists': 'top assists',
            'rating': 'highest rated',
            'ratings': 'highest rated',
            'sofascore': 'sofascore rating',
        }
        stat_query = stat_mapping.get(stat.lower(), stat)
        query_parts.append(f"most {stat_query}")
    elif player:
        query_parts.append(player)
    else:
        query_parts.append('top players')
    
    if league:
        query_parts.append(league)
    
    if season:
        query_parts.append(season)
    
    if club:
        query_parts.append(club)
    
    query = ' '.join(query_parts)
    
    # Use ask function with full format, then limit rows
    result = await ask({'query': query, 'format': 'full'}, ctx)
    
    if result.get('error'):
        return result
    
    # Process and limit results
    tables = result.get('tables', [])
    if tables:
        first_table = tables[0]
        first_table['rows'] = first_table['rows'][:limit]
        first_table['row_count'] = len(first_table['rows'])
        
        return {
            'error': None,
            'query': query,
            'headers': first_table['headers'],
            'rows': first_table['rows'],
            'row_count': first_table['row_count'],
            'text': format_table_as_text(first_table),
            'other_tables_count': len(tables) - 1
        }
    
    return result


async def get_standings(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Get league standings/table.
    
    Args:
        params: Dictionary containing:
            - league: League name like 'premier league', 'la liga', 'champions league'
            - season: Season string like '2023-24' (optional)
            
    Returns:
        Dictionary with standings table
    """
    league = params.get('league', '').strip()
    season = params.get('season', '').strip()
    
    if not league:
        return {
            'error': 'missing_league',
            'message': 'League parameter is required'
        }
    
    query_parts = [league, 'standings']
    if season:
        query_parts.append(season)
    
    query = ' '.join(query_parts)
    
    result = await ask({'query': query, 'format': 'full'}, ctx)
    
    if result.get('error'):
        return result
    
    # Look for standings table (usually has PTS, W, D, L columns)
    tables = result.get('tables', [])
    for table in tables:
        headers = [h.upper() for h in table.get('headers', [])]
        if 'PTS' in headers or 'POINTS' in headers:
            return {
                'error': None,
                'query': query,
                'league': league,
                'season': season if season else 'current',
                'headers': table['headers'],
                'rows': table['rows'],
                'row_count': table['row_count'],
                'text': format_table_as_text(table)
            }
    
    # Fallback to first table if no standings table found
    if tables:
        first_table = tables[0]
        return {
            'error': None,
            'query': query,
            'headers': first_table['headers'],
            'rows': first_table['rows'],
            'row_count': first_table['row_count'],
            'text': format_table_as_text(first_table)
        }
    
    return {
        'error': 'no_standings',
        'message': 'Could not find standings data',
        'query': query
    }


async def head_to_head(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Get head-to-head match history between two teams.
    
    Args:
        params: Dictionary containing:
            - team1: First team name
            - team2: Second team name
            - season: Season string (optional)
            
    Returns:
        Dictionary with head-to-head results
    """
    team1 = params.get('team1', '').strip()
    team2 = params.get('team2', '').strip()
    season = params.get('season', '').strip()
    
    if not team1 or not team2:
        return {
            'error': 'missing_teams',
            'message': 'Both team1 and team2 parameters are required'
        }
    
    query_parts = [team1, 'vs', team2]
    if season:
        query_parts.append(season)
    
    query = ' '.join(query_parts)
    
    result = await ask({'query': query, 'format': 'full'}, ctx)
    
    if result.get('error'):
        return result
    
    tables = result.get('tables', [])
    if tables:
        first_table = tables[0]
        return {
            'error': None,
            'query': query,
            'team1': team1,
            'team2': team2,
            'headers': first_table['headers'],
            'rows': first_table['rows'],
            'row_count': first_table['row_count'],
            'text': format_table_as_text(first_table),
            'other_tables_count': len(tables) - 1
        }
    
    return {
        'error': 'no_data',
        'message': 'No head-to-head data found',
        'query': query
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Main entry point for StatMuse skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'ask', 'search_player_stats', 'get_standings', 'head_to_head'
            - Additional parameters specific to each function
            
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function', '').lower()
    
    if not function:
        return {
            'error': 'missing_function',
            'message': 'Function parameter is required. Use: ask, search_player_stats, get_standings, or head_to_head'
        }
    
    if function == 'ask':
        return await ask(params, ctx)
    
    elif function == 'search_player_stats':
        return await search_player_stats(params, ctx)
    
    elif function == 'get_standings':
        return await get_standings(params, ctx)
    
    elif function == 'head_to_head':
        return await head_to_head(params, ctx)
    
    else:
        return {
            'error': 'unknown_function',
            'message': f'Unknown function: {function}. Use: ask, search_player_stats, get_standings, or head_to_head'
        }