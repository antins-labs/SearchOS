"""
Basketball Reference Access Skill

Fetches basketball statistics data from www.basketball-reference.com including:
- Team rosters and season stats
- Player career statistics
- Game box scores

Uses Playwright for browser automation as the site blocks direct HTTP requests.
"""

import asyncio
import re
from typing import Any, Optional


async def _fetch_page(url: str, timeout_ms: int = 45000):
    """Fetch a page using Playwright and return the page and browser objects."""
    from playwright.async_api import async_playwright
    
    pw = async_playwright()
    playwright = await pw.start()
    browser = await playwright.chromium.launch(headless=True)
    
    try:
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
        await page.wait_for_timeout(2000)  # Wait for dynamic content
        
        return page, browser
    except Exception as e:
        await browser.close()
        raise e


async def _extract_table(page, table_id: str) -> Optional[dict]:
    """Extract a table's headers and data as a structured dict."""
    table = await page.query_selector(f'#{table_id}')
    if not table:
        return None
    
    # Get headers from thead
    thead = await table.query_selector('thead')
    headers = []
    if thead:
        header_cells = await thead.query_selector_all('th, td')
        for cell in header_cells:
            text = await cell.inner_text()
            headers.append(text.strip())
    
    # Get data rows from tbody
    tbody = await table.query_selector('tbody')
    rows_data = []
    if tbody:
        rows = await tbody.query_selector_all('tr')
        for row in rows:
            cells = await row.query_selector_all('th, td')
            row_data = []
            for cell in cells:
                text = await cell.inner_text()
                link = await cell.query_selector('a')
                if link:
                    href = await link.get_attribute('href')
                    row_data.append({
                        'text': text.strip(),
                        'href': href
                    })
                else:
                    row_data.append({'text': text.strip()})
            rows_data.append(row_data)
    
    # Get caption
    caption = await table.query_selector('caption')
    caption_text = await caption.inner_text() if caption else None
    
    return {
        'id': table_id,
        'caption': caption_text.strip() if caption_text else None,
        'headers': headers,
        'rows': rows_data,
        'row_count': len(rows_data)
    }


async def _get_team_info(page) -> dict:
    """Extract team basic info from the page."""
    info = {}
    
    # Get page title
    title = await page.title()
    info['title'] = title
    
    # Get team name from h1
    h1 = await page.query_selector('h1')
    if h1:
        h1_text = await h1.inner_text()
        info['team_name'] = h1_text.strip()
    
    # Get meta info
    meta_div = await page.query_selector('#meta')
    if meta_div:
        # Extract record, coach, etc.
        paragraphs = await meta_div.query_selector_all('p')
        for p in paragraphs:
            text = await p.inner_text()
            if 'Record:' in text:
                match = re.search(r'Record:\s*(\d+-\d+)', text)
                if match:
                    info['record'] = match.group(1)
            elif 'Coach:' in text:
                match = re.search(r'Coach:\s*(.+?)(?:\n|$)', text)
                if match:
                    info['coach'] = match.group(1).strip()
    
    return info


def _parse_team_url(url: str) -> Optional[dict]:
    """Parse team URL to extract team abbreviation and season."""
    # Pattern: /teams/{ABBR}/{SEASON}.html
    match = re.search(r'/teams/([A-Z]{3})/(\d{4})\.html', url)
    if match:
        return {
            'team_abbr': match.group(1),
            'season': match.group(2)
        }
    return None


def _parse_player_url(url: str) -> Optional[dict]:
    """Parse player URL to extract player ID."""
    # Pattern: /players/{initial}/{player_id}.html
    match = re.search(r'/players/([a-z])/([a-z]+\d{2})\.html', url)
    if match:
        return {
            'player_initial': match.group(1),
            'player_id': match.group(2)
        }
    return None


def _parse_boxscore_url(url: str) -> Optional[dict]:
    """Parse boxscore URL to extract game date and home team."""
    # Pattern: /boxscores/{YYYYMMDD0}{HOMETEAM}.html (note: there's a 0 before team)
    # OR /boxscores/{YYYYMMDD}{HOMETEAM}.html
    match = re.search(r'/boxscores/(\d{8})0?([A-Z]{3})\.html', url)
    if match:
        date_str = match.group(1)
        return {
            'game_date': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            'home_team': match.group(2)
        }
    return None


async def get_team_roster(params: dict) -> dict:
    """
    Get team roster and basic info for a given team URL.
    
    Parameters:
        url: Full URL to team page (e.g., https://www.basketball-reference.com/teams/SAC/2025.html)
        team_abbr: Team abbreviation (e.g., SAC) - optional if url provided
        season: Season year (e.g., 2025) - optional if url provided
    """
    url = params.get('url')
    team_abbr = params.get('team_abbr', '').upper()
    season = params.get('season', '')
    
    if not url and team_abbr and season:
        url = f"https://www.basketball-reference.com/teams/{team_abbr}/{season}.html"
    
    if not url:
        return {'error': 'Either url or both team_abbr and season are required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get team info
        team_info = await _get_team_info(page)
        
        # Parse URL for team/season info
        url_info = _parse_team_url(url)
        if url_info:
            team_info['team_abbr'] = url_info['team_abbr']
            team_info['season'] = url_info['season']
        
        # Extract roster table
        roster_table = await _extract_table(page, 'roster')
        
        # Extract per game stats
        per_game_table = await _extract_table(page, 'per_game_stats')
        
        return {
            'success': True,
            'team_info': team_info,
            'roster': roster_table,
            'per_game_stats': per_game_table
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch team roster: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def get_team_stats(params: dict) -> dict:
    """
    Get comprehensive team statistics for a season.
    
    Parameters:
        url: Full URL to team page
        team_abbr: Team abbreviation - optional if url provided
        season: Season year - optional if url provided
        tables: List of table IDs to fetch (default: all common tables)
    """
    url = params.get('url')
    team_abbr = params.get('team_abbr', '').upper()
    season = params.get('season', '')
    
    # Default tables to fetch
    default_tables = [
        'per_game_stats', 'totals_stats', 'per_minute_stats', 
        'per_poss', 'advanced', 'team_and_opponent', 'team_misc',
        'shooting', 'adj_shooting', 'pbp_stats', 'salaries2'
    ]
    tables_to_fetch = params.get('tables', default_tables)
    
    if not url and team_abbr and season:
        url = f"https://www.basketball-reference.com/teams/{team_abbr}/{season}.html"
    
    if not url:
        return {'error': 'Either url or both team_abbr and season are required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get team info
        team_info = await _get_team_info(page)
        
        # Parse URL for team/season info
        url_info = _parse_team_url(url)
        if url_info:
            team_info['team_abbr'] = url_info['team_abbr']
            team_info['season'] = url_info['season']
        
        # Extract requested tables
        tables_data = {}
        for table_id in tables_to_fetch:
            table_data = await _extract_table(page, table_id)
            if table_data:
                tables_data[table_id] = table_data
        
        return {
            'success': True,
            'team_info': team_info,
            'tables': tables_data
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch team stats: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def get_player_stats(params: dict) -> dict:
    """
    Get player career statistics.
    
    Parameters:
        url: Full URL to player page (e.g., https://www.basketball-reference.com/players/j/jamesle01.html)
        player_id: Player ID (e.g., jamesle01) - optional if url provided
        tables: List of table IDs to fetch (default: common player tables)
    """
    url = params.get('url')
    player_id = params.get('player_id', '')
    
    # Default tables for players
    default_tables = [
        'per_game_stats', 'totals_stats', 'per_minute_stats', 
        'per_poss', 'advanced', 'shooting', 'adj_shooting', 'pbp_stats'
    ]
    tables_to_fetch = params.get('tables', default_tables)
    
    if not url and player_id:
        # Need to determine the first letter from player_id
        initial = player_id[0].lower() if player_id else ''
        if initial:
            url = f"https://www.basketball-reference.com/players/{initial}/{player_id}.html"
    
    if not url:
        return {'error': 'Either url or player_id is required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get player info
        player_info = {}
        
        title = await page.title()
        player_info['title'] = title
        
        h1 = await page.query_selector('h1')
        if h1:
            h1_text = await h1.inner_text()
            player_info['player_name'] = h1_text.strip()
        
        # Parse URL for player info
        url_info = _parse_player_url(url)
        if url_info:
            player_info['player_id'] = url_info['player_id']
        
        # Extract requested tables
        tables_data = {}
        for table_id in tables_to_fetch:
            table_data = await _extract_table(page, table_id)
            if table_data:
                tables_data[table_id] = table_data
        
        # Also check for playoff tables
        playoff_tables = ['per_game_stats_post', 'totals_stats_post', 'per_minute_stats_post']
        for table_id in playoff_tables:
            table_data = await _extract_table(page, table_id)
            if table_data and table_data['row_count'] > 0:
                tables_data[table_id] = table_data
        
        return {
            'success': True,
            'player_info': player_info,
            'tables': tables_data
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch player stats: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def get_boxscore(params: dict) -> dict:
    """
    Get game boxscore data.
    
    Parameters:
        url: Full URL to boxscore page (e.g., https://www.basketball-reference.com/boxscores/202410240SAC.html)
        game_date: Game date in YYYYMMDD format - optional if url provided
        home_team: Home team abbreviation - optional if url provided
        include_quarters: Whether to include quarter-by-quarter stats (default: false)
    """
    url = params.get('url')
    game_date = params.get('game_date', '')
    home_team = params.get('home_team', '').upper()
    include_quarters = params.get('include_quarters', False)
    
    if not url and game_date and home_team:
        # Note: Basketball Reference uses format YYYYMMDD0{TEAM}.html
        url = f"https://www.basketball-reference.com/boxscores/{game_date}0{home_team}.html"
    
    if not url:
        return {'error': 'Either url or both game_date and home_team are required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get game info
        game_info = {}
        
        title = await page.title()
        game_info['title'] = title
        
        # Parse URL for game info
        url_info = _parse_boxscore_url(url)
        if url_info:
            game_info['game_date'] = url_info['game_date']
            game_info['home_team'] = url_info['home_team']
        
        # Extract line score (final scores)
        line_score = await _extract_table(page, 'line_score')
        
        # Extract four factors
        four_factors = await _extract_table(page, 'four_factors')
        
        # Find all team boxscore tables
        # Pattern: box-{TEAM}-{period}-basic or box-{TEAM}-{period}-advanced
        all_tables = await page.query_selector_all('table[id^="box-"]')
        
        boxscore_data = {}
        for table in all_tables:
            table_id = await table.get_attribute('id')
            if not table_id:
                continue
            
            # Skip quarter tables unless requested
            if not include_quarters:
                # Only include game totals (not q1, q2, h1, h2, q3, q4)
                if any(q in table_id for q in ['q1', 'q2', 'q3', 'q4', 'h1', 'h2']):
                    continue
            
            table_data = await _extract_table(page, table_id)
            if table_data:
                boxscore_data[table_id] = table_data
        
        return {
            'success': True,
            'game_info': game_info,
            'line_score': line_score,
            'four_factors': four_factors,
            'boxscores': boxscore_data
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch boxscore: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def get_table(params: dict) -> dict:
    """
    Get a specific table from any Basketball Reference page.
    
    Parameters:
        url: Full URL to the page
        table_id: ID of the table to extract
    """
    url = params.get('url')
    table_id = params.get('table_id')
    
    if not url:
        return {'error': 'url is required'}
    if not table_id:
        return {'error': 'table_id is required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get page title
        title = await page.title()
        
        # Extract the requested table
        table_data = await _extract_table(page, table_id)
        
        if not table_data:
            return {
                'success': False,
                'error': f'Table with id "{table_id}" not found on page',
                'page_title': title
            }
        
        return {
            'success': True,
            'page_title': title,
            'table': table_data
        }
        
    except Exception as e:
        return {'error': f'Failed to fetch table: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def list_tables(params: dict) -> dict:
    """
    List all tables with IDs on a Basketball Reference page.
    
    Parameters:
        url: Full URL to the page
    """
    url = params.get('url')
    
    if not url:
        return {'error': 'url is required'}
    
    page = None
    browser = None
    
    try:
        page, browser = await _fetch_page(url)
        
        # Get page title
        title = await page.title()
        
        # Find all tables with IDs
        tables = await page.query_selector_all('table[id]')
        
        table_list = []
        for table in tables:
            table_id = await table.get_attribute('id')
            caption = await table.query_selector('caption')
            caption_text = await caption.inner_text() if caption else None
            
            tbody = await table.query_selector('tbody')
            row_count = len(await tbody.query_selector_all('tr')) if tbody else 0
            
            # Get header count
            thead = await table.query_selector('thead')
            col_count = 0
            if thead:
                header_cells = await thead.query_selector_all('th, td')
                col_count = len(header_cells)
            
            table_list.append({
                'id': table_id,
                'caption': caption_text.strip() if caption_text else None,
                'rows': row_count,
                'columns': col_count
            })
        
        return {
            'success': True,
            'page_title': title,
            'table_count': len(table_list),
            'tables': table_list
        }
        
    except Exception as e:
        return {'error': f'Failed to list tables: {str(e)}', 'success': False}
    finally:
        if browser:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Basketball Reference skill functions.
    
    Available functions:
        - get_team_roster: Get team roster and basic stats
        - get_team_stats: Get comprehensive team statistics
        - get_player_stats: Get player career statistics
        - get_boxscore: Get game boxscore data
        - get_table: Get a specific table from any page
        - list_tables: List all tables on a page
    """
    function = params.get('function', '')
    
    if function == 'get_team_roster':
        return await get_team_roster(params)
    elif function == 'get_team_stats':
        return await get_team_stats(params)
    elif function == 'get_player_stats':
        return await get_player_stats(params)
    elif function == 'get_boxscore':
        return await get_boxscore(params)
    elif function == 'get_table':
        return await get_table(params)
    elif function == 'list_tables':
        return await list_tables(params)
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_team_roster',
                'get_team_stats', 
                'get_player_stats',
                'get_boxscore',
                'get_table',
                'list_tables'
            ]
        }