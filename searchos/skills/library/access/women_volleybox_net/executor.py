"""
Volleybox access skill for women.volleybox.net
Extracts tournament classifications, team tournaments, and team information.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page


class VolleyboxClient:
    """Client for accessing women.volleybox.net data."""
    
    BASE_URL = "https://women.volleybox.net"
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def init_browser(self):
        """Initialize browser if not already initialized."""
        if not self.browser:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            context = await self.browser.new_context()
            self.page = await context.new_page()
    
    async def close(self):
        """Close the browser."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
    
    async def get_tournament_classification(self, tournament_url: str) -> Dict[str, Any]:
        """
        Extract classification/rankings from a tournament page.
        
        Args:
            tournament_url: Full URL or tournament identifier (e.g., "women-the-olympics-2024-o30223")
        
        Returns:
            Dict with tournament info and classification list
        """
        await self.init_browser()
        
        # Normalize URL
        if not tournament_url.startswith('http'):
            tournament_url = f"{self.BASE_URL}/{tournament_url}"
        
        # Remove /classification suffix if present (it redirects anyway)
        tournament_url = tournament_url.replace('/classification', '').replace('/table', '').replace('/matches', '')
        
        try:
            await self.page.goto(tournament_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            
            html = await self.page.content()
            
            # Extract tournament name
            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            tournament_name = title_match.group(1).strip() if title_match else "Unknown Tournament"
            
            # Extract tournament ID from URL
            id_match = re.search(r'-o(\d+)', tournament_url)
            tournament_id = id_match.group(1) if id_match else None
            
            # Extract classification list
            list_pattern = re.compile(r'<ol class="items_list[^"]*"[^>]*>(.*?)</ol>', re.DOTALL)
            list_match = list_pattern.search(html)
            
            classification = []
            if list_match:
                list_html = list_match.group(1)
                item_pattern = re.compile(
                    r'<li[^>]*data-country="([^"]*)"[^>]*>.*?'
                    r'<a[^>]*href="([^"]*-t\d+)"[^>]*>([^<]+)</a>',
                    re.DOTALL
                )
                items = item_pattern.findall(list_html)
                
                for rank, (country_code, team_url, team_name) in enumerate(items, 1):
                    team_id_match = re.search(r'-t(\d+)', team_url)
                    classification.append({
                        'rank': rank,
                        'team_name': team_name.strip(),
                        'country_code': country_code,
                        'team_id': team_id_match.group(1) if team_id_match else None,
                        'team_url': f"{self.BASE_URL}{team_url}" if team_url.startswith('/') else team_url
                    })
            
            return {
                'success': True,
                'tournament_name': tournament_name,
                'tournament_id': tournament_id,
                'tournament_url': tournament_url,
                'classification': classification,
                'total_teams': len(classification)
            }
            
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'timeout',
                'error_message': f'Timeout while loading tournament page: {tournament_url}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'scrape_error',
                'error_message': str(e)
            }
    
    async def get_team_tournaments(self, team_url: str, limit: int = 50) -> Dict[str, Any]:
        """
        Extract tournaments for a team from the team page.
        
        Args:
            team_url: Full URL or team identifier (e.g., "usa-t1255")
            limit: Maximum number of tournaments to return
        
        Returns:
            Dict with team info and tournament list
        """
        await self.init_browser()
        
        # Normalize URL
        if not team_url.startswith('http'):
            team_url = f"{self.BASE_URL}/{team_url}"
        
        try:
            await self.page.goto(team_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            
            html = await self.page.content()
            
            # Extract team name
            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            team_name = title_match.group(1).strip() if title_match else "Unknown Team"
            
            # Extract team ID from URL
            id_match = re.search(r'-t(\d+)', team_url)
            team_id = id_match.group(1) if id_match else None
            
            # Extract tournament links
            tournament_pattern = re.compile(
                r'<a[^>]*href="(https://women\.volleybox\.net/[^"]*-o\d+[^"]*)"[^>]*>([^<]{3,}?)</a>',
                re.IGNORECASE
            )
            
            tournaments_raw = tournament_pattern.findall(html)
            
            # Remove duplicates while preserving order
            seen = set()
            tournaments = []
            for href, name in tournaments_raw:
                if href not in seen and len(name.strip()) > 2:
                    seen.add(href)
                    
                    # Extract tournament ID
                    tour_id_match = re.search(r'-o(\d+)', href)
                    tour_id = tour_id_match.group(1) if tour_id_match else None
                    
                    tournaments.append({
                        'name': name.strip(),
                        'tournament_id': tour_id,
                        'url': href
                    })
                    
                    if len(tournaments) >= limit:
                        break
            
            return {
                'success': True,
                'team_name': team_name,
                'team_id': team_id,
                'team_url': team_url,
                'tournaments': tournaments,
                'total_tournaments': len(tournaments)
            }
            
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'timeout',
                'error_message': f'Timeout while loading team page: {team_url}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'scrape_error',
                'error_message': str(e)
            }
    
    async def get_team_info(self, team_url: str) -> Dict[str, Any]:
        """
        Get basic information about a team.
        
        Args:
            team_url: Full URL or team identifier
        
        Returns:
            Dict with team information
        """
        await self.init_browser()
        
        # Normalize URL
        if not team_url.startswith('http'):
            team_url = f"{self.BASE_URL}/{team_url}"
        
        try:
            await self.page.goto(team_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(2)
            
            html = await self.page.content()
            body_text = await self.page.inner_text('body')
            
            # Extract basic info from the page text
            lines = [line.strip() for line in body_text.split('\n') if line.strip()]
            
            # Find relevant information
            team_name = None
            tournaments_count = None
            matches_count = None
            followers_count = None
            ranking = None
            
            for i, line in enumerate(lines):
                if i == 10 and 'USA national team' in line:  # Example
                    team_name = line.replace(' national team', '')
                elif line == 'Tournaments' and i + 1 < len(lines):
                    try:
                        tournaments_count = int(lines[i + 1])
                    except:
                        pass
                elif line == 'Matches' and i + 1 < len(lines):
                    try:
                        matches_count = int(lines[i + 1])
                    except:
                        pass
                elif line == 'Followers' and i + 1 < len(lines):
                    try:
                        followers_count = int(lines[i + 1])
                    except:
                        pass
                elif line == 'Ranking' and i + 1 < len(lines):
                    try:
                        ranking = int(lines[i + 1])
                    except:
                        pass
            
            # Extract tournament name from h1
            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if title_match:
                team_name = title_match.group(1).strip()
            
            # Extract team ID
            id_match = re.search(r'-t(\d+)', team_url)
            team_id = id_match.group(1) if id_match else None
            
            return {
                'success': True,
                'team_name': team_name,
                'team_id': team_id,
                'team_url': team_url,
                'tournaments_count': tournaments_count,
                'matches_count': matches_count,
                'followers_count': followers_count,
                'ranking': ranking
            }
            
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'timeout',
                'error_message': f'Timeout while loading team page: {team_url}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'scrape_error',
                'error_message': str(e)
            }


# Global client instance
_client: Optional[VolleyboxClient] = None


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute volleybox data extraction.
    
    Args:
        params: Dictionary with:
            - function: One of "get_tournament_classification", "get_team_tournaments", "get_team_info"
            - tournament_url: Tournament URL or ID (for get_tournament_classification)
            - team_url: Team URL or ID (for get_team_tournaments, get_team_info)
            - limit: Max tournaments to return (for get_team_tournaments)
        ctx: Context (unused)
    
    Returns:
        Dict with success status and requested data
    """
    global _client
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'missing_function',
            'error_message': 'Function parameter is required'
        }
    
    # Create or reuse client
    if _client is None:
        _client = VolleyboxClient()
    
    try:
        if function == 'get_tournament_classification':
            tournament_url = params.get('tournament_url')
            if not tournament_url:
                return {
                    'success': False,
                    'error': 'missing_tournament_url',
                    'error_message': 'tournament_url parameter is required'
                }
            
            result = await _client.get_tournament_classification(tournament_url)
            return result
            
        elif function == 'get_team_tournaments':
            team_url = params.get('team_url')
            if not team_url:
                return {
                    'success': False,
                    'error': 'missing_team_url',
                    'error_message': 'team_url parameter is required'
                }
            
            limit = params.get('limit', 50)
            result = await _client.get_team_tournaments(team_url, limit)
            return result
            
        elif function == 'get_team_info':
            team_url = params.get('team_url')
            if not team_url:
                return {
                    'success': False,
                    'error': 'missing_team_url',
                    'error_message': 'team_url parameter is required'
                }
            
            result = await _client.get_team_info(team_url)
            return result
            
        else:
            return {
                'success': False,
                'error': 'invalid_function',
                'error_message': f'Unknown function: {function}'
            }
    
    finally:
        # Clean up after each request
        if _client:
            await _client.close()
            _client = None