"""
LibraryTechnology.org Academic Library Rankings Access Skill

Fetches academic library rankings and statistics from librarytechnology.org.
Uses a Safari-like User-Agent as the site blocks common bot user agents.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Any


# Valid class filter values
CLASS_FILTERS = {
    'arl': 'Association of Research Libraries',
    'aserl': 'Association of Southeastern Research Libraries',
    'elite': 'Elite Academic Libraries',
    'all': 'All US Academic Libraries',
    '1': "Associate's Colleges: High Transfer-High Traditional",
    '2': "Associate's Colleges: High Transfer-Mixed Traditional/Nontraditional",
    '3': "Associate's Colleges: High Transfer-High Nontraditional",
    '4': "Associate's Colleges: Mixed Transfer/Career & Technical-High Traditional",
    '5': "Associate's Colleges: Mixed Transfer/Career & Technical-Mixed Traditional/Nontraditional",
    '6': "Associate's Colleges: Mixed Transfer/Career & Technical-High Nontraditional",
    '7': "Associate's Colleges: High Career and Technical-High Traditional",
    '8': "Associate's Colleges: High Career and Technical-Mixed Traditional/Nontraditional",
    '9': "Associate's Colleges: High Career and Technical-High Nontraditional",
    '10': 'Special Focus Two-Year: Health Professions',
    '11': 'Special Focus Two-Year: Technical Professions',
    '12': 'Special Focus Two-Year: Arts and Design',
    '13': 'Special Focus Two-Year: Other Fields',
    '14': "Baccalaureate/Associate's Colleges: Associate's Dominant",
    '15': 'Doctoral Universities: Very High Research Activity',
    '16': 'Doctoral Universities: High Research Activity',
    '17': 'Doctoral/Professional Universities',
    '18': "Master's Colleges and Universities: Larger Programs",
    '19': "Master's Colleges and Universities: Medium Programs",
    '20': "Master's Colleges and Universities: Small Programs",
    '21': "Baccalaureate Colleges: Arts and Sciences Focus",
    '22': 'Baccalaureate Colleges: Diverse Fields',
    '23': "Baccalaureate/Associate's Colleges: Mixed Baccalaureate/Associate's",
    '24': 'Special Focus Four-Year: Faith-Related Institutions',
    '25': 'Special Focus Four-Year: Medical Schools and Centers',
    '26': 'Special Focus Four-Year: Other Health Professions Schools',
    '27': 'Special Focus Four-Year: Engineering Schools',
    '28': 'Special Focus Four-Year: Other Technology-Related Schools',
    '29': 'Special Focus Four-Year: Business and Management Schools',
    '30': 'Special Focus Four-Year: Arts, Music and Design Schools',
    '31': 'Special Focus Four-Year: Law Schools',
    '32': 'Special Focus Four-Year: Other Special Focus Institutions',
    '33': 'Tribal Colleges',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

BASE_URL = 'https://librarytechnology.org/libraries/nces/rankings/'


async def _fetch_url(url: str) -> str:
    """Fetch URL with proper headers"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        resp.raise_for_status()
        return resp.text


async def _get_rankings(class_filter: str = None) -> dict:
    """Extract academic library rankings"""
    if class_filter:
        url = f'{BASE_URL}index.pl?class={class_filter}'
    else:
        url = BASE_URL
    
    try:
        html = await _fetch_url(url)
    except Exception as e:
        return {'error': f'Failed to fetch data: {str(e)}', 'count': 0, 'libraries': []}
    
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    if not tables:
        return {'error': 'No data tables found on page', 'count': 0, 'libraries': []}
    
    # First table is the rankings table
    ranking_table = tables[0]
    rows = ranking_table.find_all('tr')
    
    # Get year from first row
    year_info = rows[0].get_text(strip=True) if rows else "Unknown"
    
    # Get headers from second row
    columns = []
    if len(rows) > 1:
        for th in rows[1].find_all('th'):
            columns.append(th.get_text(strip=True))
    
    # Extract libraries from remaining rows
    libraries = []
    for row in rows[2:]:
        ths = row.find_all('th')
        tds = row.find_all('td')
        
        # First TH is institution name, then 7 TDs for data
        if ths and len(tds) >= 7:
            institution = ths[0].get_text(strip=True)
            link = ths[0].find('a')
            
            lib = {
                'rank': tds[0].get_text(strip=True),
                'institution': institution,
                'library_id': tds[1].get_text(strip=True),
                'ipedes_libid': tds[2].get_text(strip=True),
                'ils_lsp': tds[3].get_text(strip=True),
                'personnel': tds[4].get_text(strip=True),
                'total_volumes': tds[5].get_text(strip=True),
                'total_budget': tds[6].get_text(strip=True),
            }
            
            if link and link.get('href'):
                lib['detail_url'] = f"https://librarytechnology.org{link['href']}"
            
            libraries.append(lib)
    
    # Extract summary statistics from second table if present
    summary = {}
    if len(tables) >= 2:
        for row in tables[1].find_all('tr'):
            ths = row.find_all('th')
            tds = row.find_all('td')
            if ths and tds:
                key = ths[0].get_text(strip=True)
                value = tds[-1].get_text(strip=True)
                if key and value:
                    summary[key] = value
    
    result = {
        'year': year_info,
        'columns': columns,
        'count': len(libraries),
        'libraries': libraries,
        'class_filter': class_filter,
        'class_name': CLASS_FILTERS.get(class_filter, 'Default (ARL)'),
    }
    
    if summary:
        result['summary'] = summary
    
    return result


async def _get_library_detail(library_id: str) -> dict:
    """Extract detailed statistics for a specific library"""
    url = f'https://librarytechnology.org/libraries/nces/{library_id}'
    
    try:
        html = await _fetch_url(url)
    except Exception as e:
        return {'error': f'Failed to fetch data: {str(e)}', 'library_id': library_id}
    
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    if not tables:
        return {'error': 'No data found for this library', 'library_id': library_id}
    
    # Get institution name from first table
    institution_name = ""
    if tables:
        first_row = tables[0].find('tr')
        if first_row:
            th = first_row.find('th')
            if th:
                institution_name = th.get_text(strip=True)
    
    result = {
        'library_id': library_id,
        'institution': institution_name,
        'detail_url': url,
        'statistics': []
    }
    
    # Parse all tables into structured data
    for table in tables:
        table_data = {'rows': []}
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['th', 'td'])
            row_data = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            if row_data:
                table_data['rows'].append(row_data)
        
        if table_data['rows']:
            result['statistics'].append(table_data)
    
    return result


async def _get_available_classes() -> dict:
    """Get list of available library class filters"""
    return {
        'classes': [
            {'value': value, 'label': label}
            for value, label in CLASS_FILTERS.items()
        ],
        'count': len(CLASS_FILTERS)
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the requested function.
    
    Functions:
        get_rankings: Get library rankings by class filter
        get_library_detail: Get detailed statistics for a specific library
        get_available_classes: Get list of available class filters
    """
    function = params.get('function', '')
    
    if function == 'get_rankings':
        class_filter = params.get('class_filter')
        
        if class_filter and class_filter not in CLASS_FILTERS:
            return {
                'error': f'Invalid class_filter. Valid values: {", ".join(CLASS_FILTERS.keys())}',
                'hint': 'Use get_available_classes to see all options'
            }
        
        return await _get_rankings(class_filter)
    
    elif function == 'get_library_detail':
        library_id = params.get('library_id')
        
        if not library_id:
            return {'error': 'library_id parameter is required'}
        
        return await _get_library_detail(library_id)
    
    elif function == 'get_available_classes':
        return await _get_available_classes()
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': ['get_rankings', 'get_library_detail', 'get_available_classes']
        }