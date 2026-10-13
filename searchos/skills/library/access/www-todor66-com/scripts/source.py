"""
Todor66.com Historical Volleyball Tournament Data Extractor

Extracts structured tournament data from todor66.com volleyball pages including:
- Tournament metadata (title, dates, winner)
- Finals results with set scores
- Final rankings
- Group stage standings and match results
- Team rosters
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import re


async def fetch_page(url: str, session: Optional[aiohttp.ClientSession] = None) -> str:
    """Fetch HTML content from a URL"""
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            html = await resp.text()
            return html
    finally:
        if close_session:
            await session.close()


def extract_tournament_metadata(soup: BeautifulSoup, url: str) -> dict:
    """Extract tournament title, dates, and winner from page"""
    metadata = {
        'url': url,
        'title': None,
        'year': None,
        'dates': None,
        'winner': None
    }
    
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        metadata['title'] = title_text
        
        # Extract year
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title_text)
        if year_match:
            metadata['year'] = year_match.group(1)
        
        # Extract dates (format: dd-dd.mm or dd-dd month)
        dates_match = re.search(r'(\d{1,2})[-\.](\d{1,2})\.(\d{2})', title_text)
        if dates_match:
            metadata['dates'] = dates_match.group(0)
        
        # Extract winner
        winner_match = re.search(r'Winner\s+(.+?)(?:\s*$|\s*-\s)', title_text)
        if winner_match:
            metadata['winner'] = winner_match.group(1).strip()
    
    return metadata


def parse_match_result(cells: list) -> Optional[dict]:
    """Parse a match result row into structured data"""
    cell_texts = [c.get_text(strip=True) for c in cells]
    
    if len(cell_texts) < 6:
        return None
    
    # Skip headers and section titles
    first = cell_texts[0]
    if first in ['Game', 'Finals', 'Final Ranking', '']:
        return None
    
    # Check if this looks like a match (first cell is a round identifier or date)
    if first in ['Final', '3-4', '5-6', '1/2', '5-8'] or re.match(r'\d{2}\.\d{2}', first):
        try:
            result = {
                'round': cell_texts[0],
                'date': cell_texts[1] if len(cell_texts) > 1 else None,
                'time': cell_texts[2] if len(cell_texts) > 2 else None,
                'team1': cell_texts[3] if len(cell_texts) > 3 else None,
                'score': cell_texts[4] if len(cell_texts) > 4 else None,
                'team2': cell_texts[5] if len(cell_texts) > 5 else None,
            }
            
            # Parse score into sets won
            if result['score']:
                score_match = re.match(r'(\d+)-(\d+)', result['score'])
                if score_match:
                    result['sets_won_team1'] = int(score_match.group(1))
                    result['sets_won_team2'] = int(score_match.group(2))
            
            # Parse set scores if available (columns g1-g5)
            if len(cell_texts) > 7:
                set_scores = []
                for i in range(7, min(len(cell_texts), 12)):
                    score = cell_texts[i]
                    if score and re.match(r'\d+-\d+', score):
                        set_scores.append(score)
                if set_scores:
                    result['set_scores'] = set_scores
            
            # Parse total points if available
            if len(cell_texts) > 6:
                pts = cell_texts[6]
                if pts and re.match(r'\d+-\d+', pts):
                    result['total_points'] = pts
            
            # Only return if we have valid teams
            if result.get('team1') and result.get('team2') and result.get('score'):
                return result
                
        except Exception:
            pass
    
    return None


def extract_finals_results(soup: BeautifulSoup) -> list:
    """Extract finals/knockout stage results"""
    results = []
    seen = set()  # Track unique matches
    
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        
        # Check if this table contains finals matches
        table_text = table.get_text()
        if 'Final' not in table_text or 'Game' not in table_text:
            continue
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 6:
                continue
            
            match = parse_match_result(cells)
            if match:
                # Create unique key to avoid duplicates
                key = f"{match['round']}-{match['team1']}-{match['team2']}"
                if key not in seen:
                    seen.add(key)
                    results.append(match)
    
    return results


def is_team_name(name: str) -> bool:
    """
    Determine if a name is likely a team name vs a player name.
    Team names are typically countries or multi-word names.
    Player names often have certain patterns.
    """
    # Known team names (common in volleyball)
    teams = {
        'Brazil', 'China', 'Italy', 'Japan', 'Germany', 'Poland', 'Cuba',
        'United States', 'Russia', 'South Korea', 'Netherlands', 'Serbia',
        'Thailand', 'Dominican Republic', 'Turkey', 'USA', 'Czech Republic',
        'Bulgaria', 'Romania', 'France', 'Spain', 'Greece', 'Egypt',
        'Kenya', 'Algeria', 'Cameroon', 'Nigeria', 'Tunisia', 'Morocco',
        'Argentina', 'Peru', 'Venezuela', 'Colombia', 'Mexico', 'Canada',
        'Puerto Rico', 'Costa Rica', 'Trinidad & Tobago', 'Guatemala'
    }
    
    if name in teams:
        return True
    
    # Multi-word names are likely teams (e.g., "United States")
    if len(name.split()) > 1:
        return True
    
    # All caps suggests team abbreviation
    if name.isupper() and len(name) > 2:
        return True
    
    return False


def extract_final_rankings(soup: BeautifulSoup) -> list:
    """Extract final tournament rankings"""
    rankings = []
    seen = set()  # Track unique entries
    
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        
        # Check if this is a ranking table
        table_text = table.get_text()
        if 'Final Ranking' not in table_text:
            continue
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [c.get_text(strip=True) for c in cells]
            first_cell = cell_texts[0]
            
            # Skip headers and non-ranking rows
            if first_cell in ['Final Ranking', 'w', 'l', 'gf', 'ga', 'points', 'ratio', 'WR.', '']:
                continue
            
            # Skip explanatory text
            if 'eliminated' in first_cell.lower() or 'best no participating' in first_cell.lower():
                continue
            
            # Skip entries without enough columns (need wins/losses data columns)
            if len(cell_texts) < 3:
                continue
            
            # Match patterns like "1. Brazil"
            rank_match = re.match(r'^(\d+)\.\s+(.+)$', first_cell)
            if rank_match:
                rank = int(rank_match.group(1))
                team_name = rank_match.group(2).strip()
                
                # Check if second column is numeric (wins) - this confirms it's a ranking table
                if len(cell_texts) < 2 or not cell_texts[1].isdigit():
                    continue
                
                # Filter out player names - check if this looks like a team
                if not is_team_name(team_name):
                    continue
                
                if team_name and len(team_name) > 0:
                    key = f"{rank}-{team_name}"
                    if key not in seen:
                        seen.add(key)
                        
                        ranking_entry = {
                            'rank': rank,
                            'team': team_name
                        }
                        
                        # Extract wins/losses
                        try:
                            if cell_texts[1].isdigit():
                                ranking_entry['wins'] = int(cell_texts[1])
                            if len(cell_texts) > 2 and cell_texts[2].isdigit():
                                ranking_entry['losses'] = int(cell_texts[2])
                        except (ValueError, IndexError):
                            pass
                        
                        rankings.append(ranking_entry)
    
    # Sort by rank
    rankings.sort(key=lambda x: x['rank'])
    
    return rankings


def extract_group_standings(soup: BeautifulSoup) -> dict:
    """Extract group stage standings"""
    groups = {}
    current_group = None
    
    tables = soup.find_all('table')
    for table in tables:
        text = table.get_text()
        
        # Look for group tables
        if 'Group' not in text or 'w' not in text:
            continue
        
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [c.get_text(strip=True) for c in cells]
            first_cell = cell_texts[0]
            
            # Check for group header
            group_match = re.match(r'^Group\s+([A-Z])', first_cell)
            if group_match:
                current_group = group_match.group(1)
                continue
            
            # Skip headers
            if first_cell in ['Team', 'w', 'l', 'gf', 'ga', 'ratio', '']:
                continue
            
            # Match patterns like "1. China"
            rank_match = re.match(r'^(\d+)\.\s+(.+)$', first_cell)
            if rank_match and current_group and len(cell_texts) >= 3:
                position = int(rank_match.group(1))
                team = rank_match.group(2).strip()
                
                # Check if second column is numeric (wins)
                if not cell_texts[1].isdigit():
                    continue
                
                # Filter out player names
                if not is_team_name(team):
                    continue
                
                standing = {
                    'position': position,
                    'team': team
                }
                
                # Try to extract win/loss record
                try:
                    if cell_texts[1].isdigit():
                        standing['wins'] = int(cell_texts[1])
                    if len(cell_texts) > 2 and cell_texts[2].isdigit():
                        standing['losses'] = int(cell_texts[2])
                except (ValueError, IndexError):
                    pass
                
                if current_group not in groups:
                    groups[current_group] = []
                
                # Check for duplicates
                if not any(s['team'] == team for s in groups[current_group]):
                    groups[current_group].append(standing)
    
    # Sort each group by position
    for group in groups.values():
        group.sort(key=lambda x: x['position'])
    
    return groups


def extract_group_matches(soup: BeautifulSoup) -> dict:
    """Extract group stage match results"""
    matches_by_group = {}
    current_group = None
    seen = {}  # Track unique matches per group
    
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]
            
            if not cell_texts:
                continue
            
            first_cell = cell_texts[0]
            
            # Skip header rows
            if first_cell in ['date', 'time', 'Game', 'Team', '']:
                continue
            
            # Check if this row defines a group
            group_match = re.match(r'^Group\s+([A-Z])', first_cell)
            if group_match:
                current_group = group_match.group(1)
                if current_group not in matches_by_group:
                    matches_by_group[current_group] = []
                    seen[current_group] = set()
                continue
            
            # Check if this looks like a date-prefixed match row (group stage)
            if current_group and re.match(r'\d{2}\.\d{2}', first_cell):
                if len(cells) >= 6:
                    match = parse_match_result(cells)
                    if match and match.get('team1') and match.get('team2'):
                        key = f"{match['team1']}-{match['team2']}"
                        if key not in seen[current_group]:
                            seen[current_group].add(key)
                            matches_by_group[current_group].append(match)
    
    return matches_by_group


def extract_team_rosters(soup: BeautifulSoup) -> dict:
    """Extract team rosters/lineups"""
    rosters = {}
    
    # This would require more specific HTML analysis
    # For now, we'll skip roster extraction as it needs more detailed parsing
    # and the data is less structured than other elements
    
    return rosters


def parse_tournament_page(html: str, url: str) -> dict:
    """Parse a complete tournament page and extract all structured data"""
    soup = BeautifulSoup(html, 'html.parser')
    
    tournament_data = {
        'metadata': extract_tournament_metadata(soup, url),
        'finals_results': extract_finals_results(soup),
        'final_rankings': extract_final_rankings(soup),
        'group_standings': extract_group_standings(soup),
        'group_matches': extract_group_matches(soup),
        'team_rosters': extract_team_rosters(soup),
        'raw_html_length': len(html)
    }
    
    # Add summary stats
    tournament_data['summary'] = {
        'total_finals_matches': len(tournament_data['finals_results']),
        'total_ranked_teams': len(tournament_data['final_rankings']),
        'total_groups': len(tournament_data['group_standings']),
        'total_teams_with_rosters': len(tournament_data['team_rosters'])
    }
    
    return tournament_data


def discover_tournament_urls(base_url: str, html: str) -> list:
    """Find related tournament URLs from the page"""
    soup = BeautifulSoup(html, 'html.parser')
    urls = []
    
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        # Look for links to other tournaments
        if text and ('Montreux' in text or 'montreux' in href.lower() or 
                     re.search(r'\d{4}', text)):  # Year in link text
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/'):
                from urllib.parse import urljoin
                full_url = urljoin(base_url, href)
            else:
                from urllib.parse import urljoin
                full_url = urljoin(base_url, href)
            
            if full_url not in [u['url'] for u in urls]:
                urls.append({'url': full_url, 'text': text})
    
    return urls[:20]  # Limit to 20


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Todor66 volley data extractor.
    
    Expects params with:
        - function: str - The function to call
        - url: str - Tournament page URL (for get_tournament, parse_page)
        - html: str - Raw HTML content (for parse_html)
    """
    
    function = params.get("function")
    if not function:
        return {"error": "Missing required parameter: function"}
    
    if function == "get_tournament":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        try:
            html = await fetch_page(url)
            data = parse_tournament_page(html, url)
            
            # Also find related tournaments
            related = discover_tournament_urls(url, html)
            data['related_tournaments'] = related
            
            return {"success": True, "data": data}
            
        except aiohttp.ClientError as e:
            return {"error": f"Failed to fetch page: {str(e)}", "url": url}
        except Exception as e:
            return {"error": f"Parse error: {str(e)}", "url": url}
    
    elif function == "parse_html":
        html = params.get("html")
        url = params.get("url", "unknown")
        
        if not html:
            return {"error": "Missing required parameter: html"}
        
        try:
            data = parse_tournament_page(html, url)
            related = discover_tournament_urls(url, html)
            data['related_tournaments'] = related
            
            return {"success": True, "data": data}
            
        except Exception as e:
            return {"error": f"Parse error: {str(e)}"}
    
    elif function == "get_finals":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        try:
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            finals = extract_finals_results(soup)
            
            return {
                "success": True,
                "data": {
                    "url": url,
                    "finals_results": finals,
                    "total_matches": len(finals)
                }
            }
            
        except Exception as e:
            return {"error": f"Error: {str(e)}", "url": url}
    
    elif function == "get_rankings":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        try:
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            rankings = extract_final_rankings(soup)
            
            return {
                "success": True,
                "data": {
                    "url": url,
                    "final_rankings": rankings,
                    "total_teams": len(rankings)
                }
            }
            
        except Exception as e:
            return {"error": f"Error: {str(e)}", "url": url}
    
    elif function == "get_groups":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        
        try:
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            standings = extract_group_standings(soup)
            matches = extract_group_matches(soup)
            
            return {
                "success": True,
                "data": {
                    "url": url,
                    "group_standings": standings,
                    "group_matches": matches,
                    "total_groups": len(standings)
                }
            }
            
        except Exception as e:
            return {"error": f"Error: {str(e)}", "url": url}
    
    else:
        return {"error": f"Unknown function: {function}"}