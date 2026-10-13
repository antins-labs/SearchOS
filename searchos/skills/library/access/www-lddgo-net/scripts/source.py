"""
LDDGO Country Detail Extractor

Fetches structured country information from www.lddgo.net country detail pages.
The site uses JavaScript to populate country data, so browser automation is required.

URL pattern: https://www.lddgo.net/en/common/country-detail?c={hex_name}&cca3={code}
- c: hex-encoded country name (UTF-8 bytes as hex string)
- cca3: ISO 3166-1 alpha-3 country code
"""

from __future__ import annotations
from typing import Any
from playwright.async_api import async_playwright


def _hex_encode_country_name(name: str) -> str:
    """Encode a country name to hex string as used by lddgo.net"""
    return name.encode('utf-8').hex()


def _normalize_key(key: str) -> str:
    """Normalize a table key to a valid Python identifier"""
    return key.lower().replace(' ', '_').replace('-', '_').replace('/', '_')


async def _fetch_country_detail(cca3: str, country_name: str | None = None) -> dict[str, Any]:
    """
    Fetch country details from lddgo.net.
    
    Args:
        cca3: ISO 3166-1 alpha-3 country code (e.g., 'FRA', 'USA', 'JPN')
        country_name: Country name for URL construction. If not provided, 
                      uses cca3 to derive a common name.
    
    Returns:
        Dictionary with country information or error details.
    """
    # Normalize cca3 to uppercase
    cca3 = cca3.upper().strip()
    
    # If no country name provided, try to use cca3 (the site may still work)
    if not country_name:
        country_name = cca3
    
    # Construct the URL
    hex_name = _hex_encode_country_name(country_name)
    url = f'https://www.lddgo.net/en/common/country-detail?c={hex_name}&cca3={cca3}'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
            )
            page = await context.new_page()
            
            # Navigate to the page
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for the table to be populated
            try:
                await page.wait_for_selector('#detailBody tr', timeout=10000)
            except Exception:
                # Table didn't populate - might be invalid country
                page_content = await page.content()
                if 'country' not in page_content.lower():
                    return {
                        'success': False,
                        'error': 'Country not found',
                        'cca3': cca3,
                        'url': url
                    }
                raise
            
            result = {
                'success': True,
                'url': url,
                'cca3': cca3,
            }
            
            # Extract country names
            try:
                common_name_text = await page.locator('#commonName').inner_text()
                result['common_name'] = common_name_text.replace('Common Name : ', '').strip()
            except Exception:
                result['common_name'] = None
            
            try:
                official_name_text = await page.locator('#officeName').inner_text()
                result['official_name'] = official_name_text.replace('Official Name : ', '').strip()
            except Exception:
                result['official_name'] = None
            
            # Get flag URL
            try:
                flag_src = await page.locator('#flag').get_attribute('src')
                if flag_src:
                    # Make it absolute URL
                    if flag_src.startswith('/'):
                        flag_src = f'https://www.lddgo.net{flag_src}'
                    result['flag_url'] = flag_src
            except Exception:
                pass
            
            # Extract table data
            rows = await page.locator('#detailBody tr').all()
            for row in rows:
                tds = await row.locator('td').all()
                # Each row has 4 cells: key1, value1, key2, value2
                if len(tds) >= 2:
                    key1 = await tds[0].inner_text()
                    val1 = await tds[1].inner_text()
                    result[_normalize_key(key1)] = val1
                if len(tds) >= 4:
                    key2 = await tds[2].inner_text()
                    val2 = await tds[3].inner_text()
                    result[_normalize_key(key2)] = val2
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'cca3': cca3,
                'url': url
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the LDDGO country detail skill.
    
    Dispatches based on params['function']:
    - get_country: Fetch details for a single country by cca3 code
    - get_country_by_name: Fetch details for a country by name
    """
    function = params.get('function', '')
    
    if function == 'get_country':
        cca3 = params.get('cca3', '')
        if not cca3:
            return {
                'success': False,
                'error': 'Missing required parameter: cca3'
            }
        
        country_name = params.get('country_name')
        return await _fetch_country_detail(cca3=cca3, country_name=country_name)
    
    elif function == 'get_country_by_name':
        country_name = params.get('country_name', '')
        if not country_name:
            return {
                'success': False,
                'error': 'Missing required parameter: country_name'
            }
        
        cca3 = params.get('cca3', '')
        if not cca3:
            return {
                'success': False,
                'error': 'Missing required parameter: cca3 (ISO 3166-1 alpha-3 code)'
            }
        
        return await _fetch_country_detail(cca3=cca3, country_name=country_name)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available: get_country, get_country_by_name'
        }