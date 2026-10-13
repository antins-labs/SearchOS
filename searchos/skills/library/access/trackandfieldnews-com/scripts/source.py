"""
Track & Field News Rankings Access Skill

Fetches world and U.S. ranking data from trackandfieldnews.com articles.
"""

import asyncio
import aiohttp
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


class TableParser(HTMLParser):
    """Parse HTML tables into structured data."""
    
    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self.current_table: Optional[List[List[str]]] = None
        self.current_row: Optional[List[str]] = None
        self.current_cell: Optional[str] = None
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        
    def handle_starttag(self, tag: str, attrs: List[tuple]):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th') and self.in_row:
            self.in_cell = True
            self.current_cell = ''
            
    def handle_endtag(self, tag: str):
        if tag == 'table' and self.in_table:
            if self.current_table is not None:
                self.tables.append(self.current_table)
            self.current_table = None
            self.in_table = False
        elif tag == 'tr' and self.in_row:
            if self.current_row is not None and self.current_table is not None:
                self.current_table.append(self.current_row)
            self.current_row = None
            self.in_row = False
        elif tag in ('td', 'th') and self.in_cell:
            if self.current_row is not None and self.current_cell is not None:
                self.current_row.append(self.current_cell.strip())
            self.current_cell = None
            self.in_cell = False
            
    def handle_data(self, data: str):
        if self.in_cell and self.current_cell is not None:
            self.current_cell += data


def parse_ranking_table(table: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Parse a Track & Field News ranking table into structured athlete data.
    
    The table format is:
    - Header row: "1. ATHLETE NAME (Country) (DOB, height/weight) (height-cm/weight-kg)"
    - Performance rows: time, "...", place/meet, date, optional notes
    """
    rankings = []
    current_rank = None
    current_athlete = None
    current_country = None
    current_dob = None
    performances = []
    
    for row in table:
        if not row or not row[0]:
            continue
        
        # Check if this is a ranking header (starts with number)
        rank_match = re.match(r'^(\d+)\.\s+(.+)$', row[0])
        if rank_match:
            # Save previous athlete
            if current_rank is not None:
                rankings.append({
                    'rank': current_rank,
                    'athlete': current_athlete,
                    'country': current_country,
                    'dob': current_dob,
                    'performances': performances
                })
            
            current_rank = int(rank_match.group(1))
            athlete_info = rank_match.group(2).strip()
            
            # Parse athlete info: "NAME (Country) (DOB, height/weight) (metric)"
            # Example: "NIELS LAROS (Netherlands) (4/17/05, 5-10/132) (1.78/60)"
            country_match = re.search(r'\(([^)]+)\)', athlete_info)
            if country_match:
                current_country = country_match.group(1)
                # Remove country from athlete_info for name extraction
                name_part = athlete_info[:country_match.start()].strip()
            else:
                current_country = None
                name_part = athlete_info
            
            # Extract DOB if present
            dob_match = re.search(r'\((\d+/\d+/\d+)', athlete_info)
            current_dob = dob_match.group(1) if dob_match else None
            
            current_athlete = name_part
            performances = []
            
        elif current_rank is not None and len(row) >= 2:
            # This is a performance row
            # Format: time, "...", place, date, optional marker, optional notes
            time_val = row[0] if row[0] else None
            place = row[2] if len(row) > 2 else None
            date = row[3] if len(row) > 3 else None
            notes = row[5] if len(row) > 5 else None
            
            # Skip empty rows or special rows like "(3:32.10)" which are converted times
            if time_val and not time_val.startswith('('):
                perf = {
                    'time': time_val,
                    'place': place,
                    'date': date,
                }
                if notes:
                    perf['notes'] = notes
                performances.append(perf)
    
    # Don't forget the last athlete
    if current_rank is not None:
        rankings.append({
            'rank': current_rank,
            'athlete': current_athlete,
            'country': current_country,
            'dob': current_dob,
            'performances': performances
        })
    
    return rankings


def parse_us_rankings_table(table: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Parse the U.S. rankings table which has a different format.
    
    Format is a multi-column layout with two ranking columns side by side:
    Row 0: "U.S. RANKINGS"
    Row 1: "1.", "Name (team)", "", "6.", "Name (team)"
    Row 2: "", "performances", "", "", "performances"
    
    The table has two columns of rankings side by side.
    """
    rankings = []
    
    for row_idx, row in enumerate(table):
        if not row or row[0] == 'U.S. RANKINGS' or 'U.S. RANKINGS' in row[0]:
            continue
        
        # Check if this row has ranking numbers (e.g., "1.", "2.", etc.)
        # Rankings appear at cell indices 0 and 3
        for col_idx in [0, 3]:
            if col_idx < len(row):
                cell = row[col_idx]
                rank_match = re.match(r'^(\d+)\.$', cell.strip())
                if rank_match:
                    rank = int(rank_match.group(1))
                    
                    # Next cell should be the athlete name and team
                    name_idx = col_idx + 1
                    if name_idx < len(row):
                        athlete_cell = row[name_idx].strip()
                        # Parse "Name (Team)" or "*Name (Team)"
                        is_asterisk = athlete_cell.startswith('*')
                        if is_asterisk:
                            athlete_cell = athlete_cell[1:]
                        
                        team_match = re.search(r'\(([^)]+)\)', athlete_cell)
                        if team_match:
                            team = team_match.group(1)
                            name = athlete_cell[:team_match.start()].strip()
                        else:
                            team = None
                            name = athlete_cell.strip()
                        
                        # Get performances from next row
                        performances = []
                        if row_idx + 1 < len(table):
                            next_row = table[row_idx + 1]
                            if len(next_row) > name_idx and next_row[name_idx]:
                                perf_text = next_row[name_idx]
                                # Parse performance string like "2)Eugene DL, 5)USATF, 1)Chorzów DL"
                                perf_parts = perf_text.split(',')
                                for part in perf_parts:
                                    part = part.strip()
                                    if part:
                                        perf_match = re.match(r'^(\d+[A-Za-z\-]*\)?)(.+)$', part)
                                        if perf_match:
                                            performances.append({
                                                'place': perf_match.group(1).strip(),
                                                'meet': perf_match.group(2).strip()
                                            })
                        
                        rankings.append({
                            'rank': rank,
                            'athlete': name,
                            'team': team,
                            'performances': performances
                        })
    
    # Sort by rank
    rankings.sort(key=lambda x: x['rank'])
    
    return rankings


def extract_article_content(html: str) -> str:
    """Extract article intro text from HTML."""
    # Look for entry-content div
    article_match = re.search(
        r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</article>',
        html, re.DOTALL | re.IGNORECASE
    )
    
    if article_match:
        text = article_match.group(1)
        # Remove scripts, styles, and tables
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<table[^>]*>.*?</table>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Convert HTML to text
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    return ''


def extract_title(html: str) -> str:
    """Extract page title from HTML."""
    title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1)
        # Clean up title (remove site name suffix)
        title = re.sub(r'\s*-\s*Track & Field News\s*$', '', title)
        return title.strip()
    return ''


async def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, 
            headers=headers, 
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status}: {resp.reason}")
            return await resp.text()


async def get_ranking_article(url: str) -> Dict[str, Any]:
    """
    Fetch and parse a Track & Field News ranking article.
    
    Returns structured data including:
    - title: Article title
    - intro: Article introduction text
    - world_rankings: List of world ranking entries
    - us_rankings: List of U.S. ranking entries (if present)
    """
    html = await fetch_url(url)
    
    # Parse tables
    parser = TableParser()
    parser.feed(html)
    
    # Extract title
    title = extract_title(html)
    
    # Extract article intro
    intro = extract_article_content(html)
    
    result = {
        'title': title,
        'url': url,
        'intro': intro[:2000] if intro else None,  # Limit intro length
        'world_rankings': [],
        'us_rankings': []
    }
    
    # Process tables
    for table in parser.tables:
        if not table or not table[0]:
            continue
        
        # Check if this is a world rankings table
        # World rankings have format: "1. ATHLETE NAME (Country) ..."
        first_cell = table[0][0] if table[0] else ''
        
        # Check if this is a U.S. rankings table
        if first_cell == 'U.S. RANKINGS' or 'U.S. RANKINGS' in first_cell:
            us_rankings = parse_us_rankings_table(table)
            if us_rankings:
                result['us_rankings'].extend(us_rankings)
        elif re.match(r'^\d+\.\s+\w+', first_cell):
            # This is likely a world rankings table
            rankings = parse_ranking_table(table)
            if rankings:
                result['world_rankings'].extend(rankings)
    
    return result


async def get_rankings_index(url: str = 'https://trackandfieldnews.com/track-field-news-rankings/mens-world-rankings-by-event/') -> Dict[str, Any]:
    """
    Fetch the rankings index page and extract event links.
    
    Returns a list of events with their PDF links.
    """
    html = await fetch_url(url)
    
    # Extract all links with their text
    links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html)
    
    events = []
    event_names = {
        '100 Meters', '200 Meters', '400 Meters', '800 Meters',
        '1500/Mile', 'Steeplechase', '5000 Meters', '10,000 Meters',
        '110 Hurdles', '400 Hurdles', 'Marathon', '20K Walk', '35K Walk',
        'High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump',
        'Shot', 'Discus', 'Hammer', 'Javelin', 'Decathlon'
    }
    
    for href, text in links:
        text = text.strip()
        if text in event_names:
            events.append({
                'event': text,
                'url': href,
                'type': 'pdf' if href.endswith('.pdf') else 'html'
            })
    
    return {
        'title': 'Men\'s World Rankings by Event',
        'url': url,
        'events': events
    }


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Main entry point for the Track & Field News rankings skill.
    
    Functions:
    - get_article: Fetch a specific ranking article by URL
    - get_index: Get the rankings index with event links
    """
    function = params.get('function', '')
    
    try:
        if function == 'get_article':
            url = params.get('url')
            if not url:
                return {'error': 'Missing required parameter: url'}
            
            # Validate URL
            parsed = urlparse(url)
            if parsed.netloc != 'trackandfieldnews.com':
                return {'error': 'URL must be from trackandfieldnews.com'}
            
            result = await get_ranking_article(url)
            return {'success': True, 'data': result}
        
        elif function == 'get_index':
            url = params.get('url', 'https://trackandfieldnews.com/track-field-news-rankings/mens-world-rankings-by-event/')
            gender = params.get('gender', 'men')
            
            # Adjust URL based on gender
            if gender == 'women':
                url = 'https://trackandfieldnews.com/track-field-news-rankings/womens-world-rankings-by-event/'
            
            result = await get_rankings_index(url)
            return {'success': True, 'data': result}
        
        else:
            return {'error': f'Unknown function: {function}'}
    
    except asyncio.TimeoutError:
        return {'error': 'Request timed out'}
    except aiohttp.ClientError as e:
        return {'error': f'Network error: {str(e)}'}
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}