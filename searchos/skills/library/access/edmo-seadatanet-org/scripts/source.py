"""
EDMO (European Directory of Marine Organisations) Access Skill

Fetches organization data from the SeaDataNet EDMO database.
"""

import aiohttp
import asyncio
import csv
import re
from io import StringIO
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional


BASE_URL = "https://edmo.seadatanet.org"

# Country code mapping (extracted from EDMO search page)
COUNTRY_CODES = {
    'Azerbaijan': '1',
    'Belgium': '2',
    'Bulgaria': '3',
    'Cyprus': '4',
    'Germany': '5',
    'Denmark': '6',
    'Estonia': '7',
    'Spain': '8',
    'Finland': '9',
    'France': '10',
    'United Kingdom': '11',
    'Georgia': '12',
    'Greece': '13',
    'Croatia': '14',
    'Ireland': '15',
    'Israel': '16',
    'Iceland': '17',
    'Italy': '18',
    'Kazakhstan': '19',
    'Lithuania': '20',
    'Latvia': '21',
    'Morocco': '22',
    'Malta': '23',
    'Netherlands': '24',
    'Norway': '25',
    'Poland': '26',
    'Portugal': '27',
    'Romania': '28',
    'Russian Federation': '29',
    'Sweden': '30',
    'Turkmenistan': '31',
    'Turkey': '32',
    'Ukraine': '33',
    'Madagascar': '34',
    "Côte d'Ivoire": '35',
    'Congo': '36',
    'Senegal': '37',
    'Indonesia': '38',
    'Canada': '40',
    'Japan': '41',
    'Lebanon': '42',
    'United States': '43',
    'Slovenia': '45',
    'Albania': '46',
    'Algeria': '47',
    'Tunisia': '48',
    'New Caledonia': '49',
    'Argentina': '53',
    'Australia': '54',
    'Bermuda': '58',
    'Brazil': '60',
    'Bahamas': '61',
    'Chile': '63',
    'China': '64',
    'Colombia': '65',
    'Costa Rica': '66',
    'Cuba': '67',
    'Cape Verde': '68',
    'Ecuador': '71',
    'Egypt': '72',
    'Ethiopia': '74',
    'Fiji': '75',
    'Falkland Islands (Malvinas)': '76',
    'Faroe Islands': '78',
    'French Guiana': '81',
    'Ghana': '83',
    'Greenland': '85',
    'Guinea': '87',
    'Honduras': '95',
    'Haiti': '96',
    'Isle Of Man': '97',
    'India': '98',
    'Iran, Islamic Republic of': '100',
    'Jamaica': '102',
    'Jordan': '103',
    'Kenya': '104',
    'Cambodia': '105',
    'Korea, Republic of': '108',
    'Kuwait': '109',
    'Sri Lanka': '111',
    'Lybian Arab Jamahiriya': '113',
    'Monaco': '114',
    'Myanmar': '118',
    'Mauritania': '121',
    'Mauritius': '123',
    'Maldives': '124',
    'Mexico': '125',
    'Malaysia': '126',
    'Namibia': '128',
    'Nigeria': '130',
    'New Zealand': '132',
    'Oman': '133',
    'Panama': '134',
    'Peru': '135',
    'French Polynesia': '136',
    'Philippines': '138',
    'Pakistan': '139',
    'Puerto Rico': '140',
    'Qatar': '142',
    'Saudi Arabia': '146',
    'Sudan': '149',
    'El Salvador': '159',
    'Syrian Arab Republic': '160',
    'Togo': '164',
    'Thailand': '165',
    'Tonga': '166',
    'Trinidad and Tobago': '167',
    'Taiwan, Province of China': '169',
    'Tanzania, United Republic of': '170',
    'Uruguay': '172',
    'Venezuela, Bolivarian Republic of': '174',
    'Viet Nam': '177',
    'South Africa': '181',
    'Switzerland': '184',
    'Montenegro': '214',
    'Austria': '215',
    'Unknown': '216',
    'Czech Republic': '217',
    'Angola': '218',
    'Luxembourg': '219',
    'Anguilla': '224',
    'Bangladesh': '226',
    'Belize': '227',
    'Benin': '228',
    'Bosnia and Herzegovina': '232',
    'Cameroon': '238',
    'Cook Islands': '242',
    'Hungary': '249',
    'United Arab Emirates': '281'
}

# Reverse mapping (code to name)
CODE_TO_COUNTRY = {v: k for k, v in COUNTRY_CODES.items()}


def _build_step_param(name: Optional[str] = None, country: Optional[str] = None, 
                      existing_only: bool = True) -> str:
    """
    Build the step parameter for EDMO search/export.
    
    Format:
    - 003{name} - Search by organization name
    - 000{country_code} - Filter by country (just the code, no padding needed)
    - 0021 - Filter for existing organizations only
    - Combined with underscores: 003{name}_000{country_code}_0021
    """
    parts = []
    
    if name:
        parts.append(f'003{name}')
    
    if country:
        # If country is a name, look up the code
        if country in COUNTRY_CODES:
            code = COUNTRY_CODES[country]
        elif country.isdigit():
            code = country
        else:
            code = country  # Assume it's already a code
        
        parts.append(f'000{code}')
    
    if existing_only:
        parts.append('0021')
    
    return '_'.join(parts) if parts else '0021'


def _parse_csv_export(csv_text: str) -> List[Dict[str, Any]]:
    """Parse the EDMO CSV export format."""
    lines = csv_text.strip().split('\n')
    
    # Skip the first line "Export OF QUERY RESULTS FROM EDMO."
    if lines and 'Export OF QUERY' in lines[0]:
        lines = lines[1:]
    
    # Parse CSV
    reader = csv.DictReader(StringIO('\n'.join(lines)))
    records = []
    
    for row in reader:
        if row.get('EDMO record id') and row['EDMO record id'].strip():
            record = {
                'edmo_id': row.get('EDMO record id', '').strip(),
                'name': row.get('Name', '').strip(),
                'native_name': row.get('Native name', '').strip(),
                'abbreviation': row.get('Abbreviation', '').strip(),
                'address': row.get('Address', '').strip(),
                'address2': row.get('Address 2', '').strip(),
                'zipcode': row.get('Zipcode', '').strip(),
                'city': row.get('City', '').strip(),
                'state': row.get('State', '').strip(),
                'country': row.get('Country', '').strip(),
                'email': row.get('Email', '').strip(),
                'phone': row.get('Phone', '').strip(),
                'fax': row.get('Fax', '').strip(),
                'website': row.get('Website', '').strip(),
                'url': row.get('URL', '').strip(),
                'latitude': row.get('Latitude', '').strip(),
                'longitude': row.get('Longitude', '').strip()
            }
            
            # Only add if we have meaningful data
            if record['edmo_id'] and record['name']:
                records.append(record)
    
    return records


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        return await resp.text()


async def _fetch_csv(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch CSV content with proper encoding handling."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/csv,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
        data = await resp.read()
        # Try different encodings
        for encoding in ['windows-1252', 'utf-8', 'iso-8859-1', 'latin-1']:
            try:
                return data.decode(encoding)
            except:
                continue
        return data.decode('utf-8', errors='ignore')


def _parse_detail_page(html: str) -> Dict[str, Any]:
    """Parse an EDMO organization detail page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'success': False,
        'data': {},
        'services': [],
        'metadata': {}
    }
    
    try:
        # Extract data from definition list
        dl = soup.find('dl')
        if dl:
            current_key = None
            for child in dl.children:
                if child.name == 'dt':
                    current_key = child.get_text(strip=True)
                elif child.name == 'dd' and current_key:
                    text = child.get_text(strip=True)
                    link = child.find('a')
                    if link and link.get('href'):
                        if link['href'].startswith('/report/'):
                            result['data'][current_key] = {
                                'text': text,
                                'edmo_id': link['href'].split('/report/')[-1]
                            }
                        else:
                            result['data'][current_key] = text
                    else:
                        result['data'][current_key] = text
        
        # Extract coordinates from JavaScript
        for script in soup.find_all('script'):
            if script.string and 'marker_coordinates' in script.string:
                coord_match = re.search(r'marker_coordinates\s*=\s*L\.latLng\(([0-9.-]+),([0-9.-]+)\)', script.string)
                if coord_match:
                    result['data']['coordinates'] = {
                        'latitude': float(coord_match.group(1)),
                        'longitude': float(coord_match.group(2))
                    }
        
        # Extract EDMO metadata (ID, update date, etc.)
        body_text = soup.get_text()
        
        id_match = re.search(r'EDMO record id[\s\S]*?(\d+)', body_text)
        if id_match:
            result['metadata']['edmo_id'] = id_match.group(1)
        
        update_match = re.search(r'Latest update[\s\S]*?(\d+\s+\w+\s+\d{4}[\s\d:]+(?:AM|PM))', body_text)
        if update_match:
            result['metadata']['latest_update'] = update_match.group(1).strip()
        
        centre_match = re.search(r'Collating centre[\s\n]+([^\n]+)', body_text)
        if centre_match:
            result['metadata']['collating_centre'] = centre_match.group(1).strip()
        
        # Extract service links
        buttons_section = soup.find(id='buttons')
        if buttons_section:
            for link in buttons_section.find_all('a'):
                if link.get('href'):
                    result['services'].append({
                        'name': link.get_text(strip=True),
                        'url': link['href']
                    })
        
        # Get title
        title = soup.find('title')
        if title:
            result['metadata']['title'] = title.get_text(strip=True)
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def get_organization_by_id(edmo_id: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """
    Fetch a specific organization by EDMO ID.
    
    Args:
        edmo_id: The EDMO record ID (e.g., "4830")
        session: Optional aiohttp session
    
    Returns:
        Dictionary with organization details
    """
    url = f"{BASE_URL}/report/{edmo_id}"
    
    async def _fetch():
        async with aiohttp.ClientSession() as s:
            return await _fetch_html(url, s)
    
    html = await (_fetch() if session is None else _fetch_html(url, session))
    result = _parse_detail_page(html)
    result['url'] = url
    result['edmo_id'] = edmo_id
    
    return result


async def search_organizations(
    name: Optional[str] = None,
    country: Optional[str] = None,
    existing_only: bool = True,
    limit: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None
) -> Dict[str, Any]:
    """
    Search EDMO organizations by name and/or country.
    
    Args:
        name: Organization name search string
        country: Country name or code (e.g., "Switzerland" or "184")
        existing_only: Only return currently existing organizations
        limit: Maximum number of results to return
        session: Optional aiohttp session
    
    Returns:
        Dictionary with search results
    """
    step = _build_step_param(name=name, country=country, existing_only=existing_only)
    url = f"{BASE_URL}/v_edmo/browse_export.asp?step={step}"
    
    async def _fetch():
        async with aiohttp.ClientSession() as s:
            return await _fetch_csv(url, s)
    
    csv_text = await (_fetch() if session is None else _fetch_csv(url, session))
    
    try:
        records = _parse_csv_export(csv_text)
        
        if limit:
            records = records[:limit]
        
        return {
            'success': True,
            'count': len(records),
            'records': records,
            'search_params': {
                'name': name,
                'country': country,
                'existing_only': existing_only,
                'step_param': step
            },
            'export_url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'export_url': url,
            'csv_preview': csv_text[:500] if csv_text else None
        }


async def list_all_organizations(
    existing_only: bool = True,
    limit: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None
) -> Dict[str, Any]:
    """
    List all organizations in the EDMO database.
    
    Args:
        existing_only: Only return currently existing organizations
        limit: Maximum number of results to return
        session: Optional aiohttp session
    
    Returns:
        Dictionary with all organizations
    """
    return await search_organizations(
        name=None,
        country=None,
        existing_only=existing_only,
        limit=limit,
        session=session
    )


async def get_country_list() -> Dict[str, Any]:
    """
    Get the list of available countries with their codes.
    
    Returns:
        Dictionary with country names and codes
    """
    return {
        'success': True,
        'count': len(COUNTRY_CODES),
        'countries': COUNTRY_CODES
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute EDMO query based on function parameter.
    
    Args:
        params: Dictionary containing:
            - function: One of:
                - "get_organization": Get organization by ID (requires edmo_id)
                - "search_organizations": Search by name/country
                - "list_organizations": List all organizations
                - "get_countries": Get country code mapping
            - edmo_id: EDMO record ID (for get_organization)
            - name: Organization name search string (for search_organizations)
            - country: Country name or code (for search_organizations)
            - existing_only: Filter for existing orgs (default: true)
            - limit: Maximum number of results (for search/list)
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error
    """
    function = params.get('function', '').lower()
    
    if function == 'get_organization':
        edmo_id = params.get('edmo_id')
        if not edmo_id:
            return {'success': False, 'error': 'edmo_id parameter is required'}
        
        return await get_organization_by_id(str(edmo_id))
    
    elif function == 'search_organizations':
        name = params.get('name')
        country = params.get('country')
        existing_only = params.get('existing_only', 'true').lower() != 'false'
        limit = params.get('limit')
        if limit:
            limit = int(limit)
        
        if not name and not country:
            return {'success': False, 'error': 'At least one of name or country parameter is required'}
        
        return await search_organizations(
            name=name,
            country=country,
            existing_only=existing_only,
            limit=limit
        )
    
    elif function == 'list_organizations':
        existing_only = params.get('existing_only', 'true').lower() != 'false'
        limit = params.get('limit')
        if limit:
            limit = int(limit)
        
        return await list_all_organizations(
            existing_only=existing_only,
            limit=limit
        )
    
    elif function == 'get_countries':
        return await get_country_list()
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Valid functions: get_organization, search_organizations, list_organizations, get_countries'
        }