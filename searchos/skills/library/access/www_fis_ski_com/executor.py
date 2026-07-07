"""
FIS-SKI.com Database Access Skill

This skill extracts athlete biographies and race results from the FIS (International Ski Federation) database.
The site uses server-side rendered HTML with Next.js, not a JSON API.

Supported functions:
- get_athlete_bio: Get athlete biography and results history
- get_race_results: Get detailed results for a specific race
"""

import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
import aiohttp


async def fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.text()
    except asyncio.TimeoutError:
        raise Exception(f"Timeout fetching {url}")
    except aiohttp.ClientError as e:
        raise Exception(f"HTTP error fetching {url}: {str(e)}")


def parse_athlete_bio(html: str) -> dict:
    """Parse athlete biography page HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    athlete = {
        'success': True,
        'profile': {},
        'results': []
    }
    
    # Extract profile information
    # Name
    name_elem = soup.find('h1', class_='athlete-profile__name')
    if name_elem:
        lastname_elem = name_elem.find('span', class_='athlete-profile__lastname')
        if lastname_elem:
            lastname = lastname_elem.get_text(strip=True)
            full_text = name_elem.get_text(strip=True)
            firstname = full_text.replace(lastname, '').strip()
            athlete['profile']['firstname'] = firstname
            athlete['profile']['lastname'] = lastname
            athlete['profile']['fullname'] = f"{firstname} {lastname}"
    
    # Profile picture
    avatar = soup.find('div', class_='avatar__image')
    if avatar:
        style = avatar.get('style', '')
        match = re.search(r"url\('([^']+)'\)", style)
        if match:
            athlete['profile']['image_url'] = match.group(1)
    
    # Country - check for different class names
    country_div = soup.find('div', class_='athlete-profile__country')
    if country_div:
        # Try country__name-short for code
        country_code = country_div.find('span', class_='country__name-short')
        if not country_code:
            country_code = country_div.find('span', class_='country__code')
        
        # Try country__name for full name
        country_name = country_div.find('span', class_='country__name')
        
        if country_code:
            athlete['profile']['country_code'] = country_code.get_text(strip=True)
        if country_name:
            athlete['profile']['country_name'] = country_name.get_text(strip=True)
    
    # Team - direct text content (no span wrapper)
    team_div = soup.find('div', class_='athlete-profile__team')
    if team_div:
        team_text = team_div.get_text(strip=True)
        if team_text:
            athlete['profile']['team'] = team_text
    
    # Info fields (FIS code, birthdate, etc.)
    info_div = soup.find('div', class_='athlete-profile__content')
    if info_div:
        info_items = info_div.find_all('div', class_='athlete-profile__info-item')
        for item in info_items:
            label_elem = item.find('div', class_='athlete-profile__info-label')
            value_elem = item.find('div', class_='athlete-profile__info-value')
            if label_elem and value_elem:
                label = label_elem.get_text(strip=True).lower().replace(' ', '_').replace('.', '')
                value = value_elem.get_text(strip=True)
                if value and value != '– –':
                    athlete['profile'][label] = value
    
    # Extract FIS properties from JavaScript
    fis_props_match = re.search(r'window\.fisProperties\s*=\s*({[^;]+});', html)
    if fis_props_match:
        try:
            import json
            props = json.loads(fis_props_match.group(1))
            athlete['profile']['fis_code'] = props.get('fisCode')
            athlete['profile']['gender'] = props.get('genderCode')
            athlete['profile']['discipline'] = props.get('disciplineCode')
        except:
            pass
    
    # Extract results table
    results_table = soup.find('div', id='resultdata')
    if results_table:
        body = results_table.find('div', class_='table__body')
        if body:
            rows = body.find_all('a', class_='table-row')
            
            for row in rows:
                result = {}
                
                # Extract URL and IDs
                href = row.get('href', '')
                result['url'] = href
                
                raceid_match = re.search(r'raceid=(\d+)', href)
                if raceid_match:
                    result['raceid'] = raceid_match.group(1)
                
                competitorid_match = re.search(r'competitorid=(\d+)', href)
                if competitorid_match:
                    result['competitorid'] = competitorid_match.group(1)
                
                sector_match = re.search(r'sectorcode=([^&]+)', href)
                if sector_match:
                    result['sectorcode'] = sector_match.group(1)
                
                # Parse text content
                text = row.get_text(' ', strip=True)
                parts = text.split()
                
                # Extract date (DD-MM-YYYY format)
                date_match = re.search(r'(\d{2}-\d{2}-\d{4})', text)
                if date_match:
                    result['date'] = date_match.group(1)
                
                # Parse structured data from div cells
                container = row.find('div', class_='container')
                if container:
                    all_divs = container.find_all('div', recursive=False)
                    
                    for div in all_divs:
                        classes = div.get('class', [])
                        class_str = ' '.join(classes)
                        text_content = div.get_text(strip=True)
                        
                        # Date column
                        if 'g-xs-4' in classes and 'g-sm-4' in classes:
                            if re.match(r'\d{2}-\d{2}-\d{4}', text_content):
                                result['date'] = text_content
                        
                        # Place column (hidden on small screens)
                        elif 'g-md' in classes and 'g-lg' in classes and 'hidden-sm-down' in classes:
                            if 'place' not in result and text_content and not text_content[0].isdigit():
                                result['place'] = text_content
                        
                        # Nation/Category column
                        elif 'g-sm-3' in classes and ('g-md-2' in classes or 'g-md-5' in classes):
                            if len(text_content) == 3 and text_content.isupper():
                                result['nation_code'] = text_content
                            elif text_content and len(text_content) > 3:
                                result['category'] = text_content
                        
                        # Discipline column
                        elif 'g-md-3' in classes and 'g-lg-3' in classes:
                            result['discipline'] = text_content
                        
                        # Position/Points columns
                        elif 'g-xs-6' in classes:
                            sub_divs = div.find_all('div', recursive=False)
                            if len(sub_divs) >= 1:
                                result['position'] = sub_divs[0].get_text(strip=True)
                            if len(sub_divs) >= 2:
                                result['fis_points'] = sub_divs[1].get_text(strip=True)
                            if len(sub_divs) >= 3:
                                result['cup_points'] = sub_divs[2].get_text(strip=True)
                
                if result.get('date') or result.get('raceid'):
                    athlete['results'].append(result)
    
    return athlete


def parse_race_results(html: str) -> dict:
    """Parse race results page HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    race_data = {
        'success': True,
        'venue': None,
        'event': None,
        'season': None,
        'results': []
    }
    
    # Venue
    h1 = soup.find('h1')
    if h1:
        race_data['venue'] = h1.get_text(strip=True)
    
    # Event/season from title
    title = soup.find('title')
    if title:
        title_text = title.get_text(strip=True)
        if ' - ' in title_text:
            parts = title_text.split(' - ')
            if len(parts) >= 2:
                race_data['event'] = parts[1].strip()
            if len(parts) >= 3:
                race_data['season'] = parts[2].strip()
    
    # Event info
    events_info = soup.find(id='events-info-results')
    if events_info:
        rows = events_info.find_all('div', class_='table-row')
        for row in rows:
            cells = row.find_all('div', recursive=False)
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower().replace('.', '').replace(' ', '_')
                value = cells[1].get_text(strip=True)
                race_data[label] = value
    
    # Results table
    result_rows = soup.find_all('a', class_='table-row')
    
    for row in result_rows:
        # Check if this row has a competitor link (indicates it's a result row)
        if 'competitorid=' not in row.get('href', ''):
            continue
        
        result = {}
        
        # Extract URL and competitorid
        href = row.get('href', '')
        result['url'] = href
        
        competitorid_match = re.search(r'competitorid=(\d+)', href)
        if competitorid_match:
            result['competitorid'] = competitorid_match.group(1)
        
        # Parse text content
        text = row.get_text(' ', strip=True)
        parts = text.split()
        
        if len(parts) >= 8:
            try:
                result['rank'] = int(parts[0]) if parts[0].isdigit() else parts[0]
                result['bib'] = parts[1]
                result['fis_code'] = parts[2]
                
                # Find year (4 digits between 1950-2025)
                year_idx = None
                for i, part in enumerate(parts):
                    if part.isdigit() and 1950 <= int(part) <= 2025:
                        year_idx = i
                        break
                
                if year_idx:
                    result['birth_year'] = int(parts[year_idx])
                    result['nation'] = parts[year_idx + 1] if year_idx + 1 < len(parts) else None
                    
                    # Name is between fis_code and year
                    result['athlete'] = ' '.join(parts[3:year_idx])
                    
                    # Remaining parts after nation
                    remaining = parts[year_idx + 2:]
                    
                    # Find scores (numbers at the end)
                    scores = []
                    for j in range(len(remaining) - 1, -1, -1):
                        part = remaining[j].replace(',', '.')
                        if re.match(r'^\d+\.?\d*$', part):
                            scores.insert(0, remaining[j])
                        else:
                            break
                    
                    if len(scores) >= 1:
                        try:
                            result['score'] = float(scores[0])
                        except ValueError:
                            result['score'] = scores[0]
                    if len(scores) >= 2:
                        try:
                            result['fis_points'] = float(scores[1])
                        except ValueError:
                            result['fis_points'] = scores[1]
            
            except (ValueError, IndexError) as e:
                # If parsing fails, store raw text
                result['raw'] = text
                result['parse_error'] = str(e)
        
        if result and (result.get('competitorid') or result.get('rank')):
            race_data['results'].append(result)
    
    return race_data


async def get_athlete_bio(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Get athlete biography and competition history
    
    Required params:
    - competitorid: FIS competitor ID (e.g., "226193")
    
    Optional params:
    - sectorcode: Sport sector code (default: "fs" for freestyle skiing)
    - type: Result type (default: "result")
    """
    competitorid = params.get('competitorid')
    if not competitorid:
        return {
            'success': False,
            'error': 'Missing required parameter: competitorid',
            'error_type': 'validation'
        }
    
    sectorcode = params.get('sectorcode', 'fs')
    result_type = params.get('type', 'result')
    
    url = f"https://www.fis-ski.com/DB/general/athlete-biography.html"
    url += f"?sectorcode={sectorcode}&competitorid={competitorid}&type={result_type}"
    
    try:
        html = await fetch_html(url, session)
        return parse_athlete_bio(html)
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to fetch athlete biography: {str(e)}",
            'error_type': 'network'
        }


async def get_race_results(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Get detailed results for a specific race
    
    Required params:
    - raceid: FIS race ID (e.g., "19025")
    
    Optional params:
    - sectorcode: Sport sector code (default: "FS")
    - competitorid: Filter by competitor ID (optional, used for context)
    """
    raceid = params.get('raceid')
    if not raceid:
        return {
            'success': False,
            'error': 'Missing required parameter: raceid',
            'error_type': 'validation'
        }
    
    sectorcode = params.get('sectorcode', 'FS')
    competitorid = params.get('competitorid', '')
    
    url = f"https://www.fis-ski.com/DB/general/results.html"
    url += f"?sectorcode={sectorcode}"
    if competitorid:
        url += f"&competitorid={competitorid}"
    url += f"&raceid={raceid}"
    
    try:
        html = await fetch_html(url, session)
        return parse_race_results(html)
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to fetch race results: {str(e)}",
            'error_type': 'network'
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the FIS-SKI access skill
    
    Required params:
    - function: One of "get_athlete_bio", "get_race_results"
    
    Function-specific params:
    
    get_athlete_bio:
        - competitorid: (required) FIS competitor ID
        - sectorcode: (optional) Sport sector code (default: "fs")
        - type: (optional) Result type (default: "result")
    
    get_race_results:
        - raceid: (required) FIS race ID
        - sectorcode: (optional) Sport sector code (default: "FS")
        - competitorid: (optional) Competitor ID for context
    
    Returns:
        Dictionary with 'success' boolean and either data or error information
    """
    function = params.get('function')
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'error_type': 'validation',
            'available_functions': ['get_athlete_bio', 'get_race_results']
        }
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_athlete_bio':
            return await get_athlete_bio(params, session)
        elif function == 'get_race_results':
            return await get_race_results(params, session)
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_type': 'validation',
                'available_functions': ['get_athlete_bio', 'get_race_results']
            }