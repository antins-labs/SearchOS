"""
IBAN.com Access Skill

Provides access to:
- ISO 3166-1 country codes (alpha-2, alpha-3, numeric)
- IBAN structure information for all countries
- IBAN validation (limited by free tier rate limits)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp
from bs4 import BeautifulSoup


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch a page with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.text()


def parse_country_codes(html: str) -> list[dict[str, str]]:
    """Parse ISO 3166-1 country codes from the table."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return []
    
    countries = []
    rows = table.find_all('tr')
    
    for row in rows[1:]:  # Skip header
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 4:
            country = {
                'country': cells[0].get_text(strip=True),
                'alpha_2': cells[1].get_text(strip=True),
                'alpha_3': cells[2].get_text(strip=True),
                'numeric': cells[3].get_text(strip=True),
            }
            countries.append(country)
    
    return countries


def parse_iban_structure(html: str) -> dict[str, Any]:
    """Parse IBAN structure information from both tables."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    
    result = {
        'sepa_countries': [],
        'non_sepa_countries': [],
    }
    
    for i, table in enumerate(tables):
        rows = table.find_all('tr')
        if not rows:
            continue
        
        # Determine table type from headers
        header_row = rows[0]
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
        
        for row in rows[1:]:
            cells = row.find_all('td')
            if not cells:
                continue
            
            if 'sepa' in headers:
                # Table with SEPA column (first table)
                entry = {
                    'country': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                    'code': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                    'sepa': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                    'length': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                    'account_check': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                    'branch': cells[5].get_text(strip=True) if len(cells) > 5 else '',
                    'iban_example': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                }
                result['sepa_countries'].append(entry)
            else:
                # Table without SEPA column (second table - non-SEPA)
                entry = {
                    'country': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                    'code': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                    'sepa': 'No',
                    'length': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                    'iban_example': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                }
                result['non_sepa_countries'].append(entry)
    
    return result


async def validate_iban(iban: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Validate an IBAN using iban.com checker.
    Note: Free tier has rate limits (typically a few checks per day per IP).
    """
    url = 'https://www.iban.com/iban-checker'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.iban.com',
        'Referer': url,
    }
    
    # Clean the IBAN
    clean_iban = re.sub(r'[^a-zA-Z0-9]', '', iban).upper()
    
    # First GET to establish session
    await session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30))
    
    # Then POST
    async with session.post(
        url,
        data={'iban': clean_iban},
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30)
    ) as response:
        html = await response.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check for rate limit
    alert_warning = soup.find('div', class_='alert-warning')
    if alert_warning and 'exceeded' in alert_warning.get_text().lower():
        return {
            'error': 'rate_limit_exceeded',
            'message': 'Daily rate limit exceeded for free IBAN validation service',
            'iban': clean_iban,
        }
    
    # Look for validation results
    # The page structure may vary based on whether it's valid or not
    # We'll extract what we can from the response
    
    result = {
        'iban': clean_iban,
        'country_code': clean_iban[:2] if len(clean_iban) >= 2 else '',
        'check_digits': clean_iban[2:4] if len(clean_iban) >= 4 else '',
    }
    
    # Extract any validation status from the page
    body_text = soup.get_text()
    
    # Look for success indicators
    success_patterns = [
        r'valid\s+iban',
        r'iban\s+is\s+valid',
        r'checksum\s+passed',
        r'validation\s+passed',
    ]
    
    error_patterns = [
        r'invalid\s+iban',
        r'iban\s+is\s+invalid',
        r'checksum\s+failed',
        r'validation\s+failed',
        r'incorrect',
    ]
    
    is_valid = None
    for pattern in success_patterns:
        if re.search(pattern, body_text, re.I):
            is_valid = True
            break
    
    if is_valid is None:
        for pattern in error_patterns:
            if re.search(pattern, body_text, re.I):
                is_valid = False
                break
    
    result['is_valid'] = is_valid
    result['raw_response_length'] = len(html)
    
    return result


def filter_by_country_code(data: list[dict], code: str) -> list[dict]:
    """Filter results by country code (alpha-2 or alpha-3)."""
    code = code.upper()
    return [
        item for item in data
        if item.get('alpha_2', '').upper() == code
        or item.get('alpha_3', '').upper() == code
        or item.get('code', '').upper() == code
    ]


def filter_by_country_name(data: list[dict], name: str) -> list[dict]:
    """Filter results by country name (case-insensitive partial match)."""
    name_lower = name.lower()
    return [
        item for item in data
        if name_lower in item.get('country', '').lower()
    ]


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute IBAN.com access skill.
    
    Functions:
    - get_country_codes: Get ISO 3166-1 country codes
    - get_iban_structure: Get IBAN structure information for all countries
    - validate_iban: Validate an IBAN number (rate limited)
    """
    function = params.get('function', '')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=5)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        try:
            if function == 'get_country_codes':
                # Optional filtering
                country_code = params.get('country_code', '')
                country_name = params.get('country_name', '')
                
                url = 'https://www.iban.com/country-codes'
                html = await fetch_page(url, session)
                countries = parse_country_codes(html)
                
                if country_code:
                    countries = filter_by_country_code(countries, country_code)
                elif country_name:
                    countries = filter_by_country_name(countries, country_name)
                
                return {
                    'success': True,
                    'count': len(countries),
                    'countries': countries,
                    'source_url': url,
                }
            
            elif function == 'get_iban_structure':
                # Optional filtering by country
                country_code = params.get('country_code', '')
                country_name = params.get('country_name', '')
                
                url = 'https://www.iban.com/structure'
                html = await fetch_page(url, session)
                structure_data = parse_iban_structure(html)
                
                result = {
                    'success': True,
                    'source_url': url,
                    'sepa_countries_count': len(structure_data['sepa_countries']),
                    'non_sepa_countries_count': len(structure_data['non_sepa_countries']),
                }
                
                # Filter if requested
                if country_code:
                    structure_data['sepa_countries'] = filter_by_country_code(
                        structure_data['sepa_countries'], country_code
                    )
                    structure_data['non_sepa_countries'] = filter_by_country_code(
                        structure_data['non_sepa_countries'], country_code
                    )
                elif country_name:
                    structure_data['sepa_countries'] = filter_by_country_name(
                        structure_data['sepa_countries'], country_name
                    )
                    structure_data['non_sepa_countries'] = filter_by_country_name(
                        structure_data['non_sepa_countries'], country_name
                    )
                
                result['sepa_countries'] = structure_data['sepa_countries']
                result['non_sepa_countries'] = structure_data['non_sepa_countries']
                
                return result
            
            elif function == 'validate_iban':
                iban = params.get('iban', '')
                if not iban:
                    return {
                        'error': 'Missing required parameter: iban',
                        'success': False,
                    }
                
                result = await validate_iban(iban, session)
                result['success'] = 'error' not in result
                return result
            
            else:
                return {
                    'error': f'Unknown function: {function}',
                    'success': False,
                    'available_functions': [
                        'get_country_codes',
                        'get_iban_structure',
                        'validate_iban',
                    ],
                }
        
        except aiohttp.ClientError as e:
            return {
                'error': f'HTTP error: {str(e)}',
                'success': False,
            }
        except Exception as e:
            return {
                'error': f'Unexpected error: {str(e)}',
                'success': False,
            }