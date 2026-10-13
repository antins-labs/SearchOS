"""
ISO 3166 Country Code Data Extractor

This skill extracts ISO 3166 country code information from the ISO Online Browsing Platform.
It uses Playwright browser automation to bypass Cloudflare security verification and
wait for the Vaadin JavaScript application to fully load the country data.

Supports:
- get_country: Retrieve detailed country code information by 2-letter code
"""

from typing import Any
import asyncio
import re
from playwright.async_api import async_playwright


async def _extract_country_data(country_code: str) -> dict:
    """
    Extract ISO 3166 country data for a specific country code using browser automation.
    
    Args:
        country_code: Two-letter ISO 3166-1 alpha-2 country code (e.g., 'US', 'DE', 'NL')
    
    Returns:
        Dictionary containing country code information or error details
    """
    # Normalize country code to uppercase
    country_code = country_code.upper().strip()
    
    # Validate country code format
    if not re.match(r'^[A-Z]{2}$', country_code):
        return {
            'success': False,
            'country_code': country_code,
            'error': 'Invalid country code format. Must be 2 uppercase letters (e.g., US, DE, NL)'
        }
    
    url = f"https://www.iso.org/obp/ui/#iso:code:3166:{country_code}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            # Retry logic for reliability
            max_retries = 2
            text_content = ""
            
            for attempt in range(max_retries + 1):
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                try:
                    # Load page
                    try:
                        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                    except Exception:
                        # Continue even if timeout occurs, content may still load
                        pass
                    
                    # Wait for Vaadin app to render content
                    # The ISO OBP is a Vaadin application that loads data asynchronously
                    for i in range(15):
                        await asyncio.sleep(1)
                        text = await page.locator('body').inner_text()
                        tables = await page.locator('table').count()
                        
                        # Check if data is loaded (tables indicate content is ready)
                        if len(text) > 500 and tables >= 1:
                            text_content = text
                            break
                    
                    # If we got meaningful content, return it
                    if len(text_content) > 500:
                        break
                    
                    # Otherwise, try to get whatever text we have
                    text_content = await page.locator('body').inner_text()
                    if len(text_content) > 500:
                        break
                        
                finally:
                    await context.close()
            
            # Parse the extracted text
            return _parse_country_data(text_content, country_code)
            
        finally:
            await browser.close()


def _parse_country_data(text: str, country_code: str) -> dict:
    """
    Parse the raw text content into structured country data.
    
    Args:
        text: Raw text content from the ISO OBP page
        country_code: The requested country code
    
    Returns:
        Dictionary with parsed country information
    """
    data = {
        'success': False,
        'country_code': country_code.upper(),
        'source': 'ISO 3166-1',
        'source_url': f"https://www.iso.org/obp/ui/#iso:code:3166:{country_code.upper()}"
    }
    
    if not text or len(text) < 100:
        data['error'] = 'Failed to load page content. The page may be temporarily unavailable.'
        return data
    
    # Check if the country code exists in the response
    if country_code.upper() not in text:
        data['error'] = f'Country code "{country_code}" not found in ISO 3166-1.'
        return data
    
    # Extract fields using regex patterns
    patterns = {
        'alpha_2_code': r'Alpha-2 code\s*\n([A-Z]{2})',
        'alpha_3_code': r'Alpha-3 code\s*\n([A-Z]{3})',
        'numeric_code': r'Numeric code\s*\n(\d+)',
        'short_name': r'Short name\s*\n(.+?)(?=\n)',
        'short_name_lower': r'Short name lower case\s*\n(.+?)(?=\n)',
        'full_name': r'Full name\s*\n(.+?)(?=\n)',
        'independent': r'Independent\s*\n(Yes|No)',
        'status': r'Status\s*\n(.+?)(?=\n)',
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            # Clean up the value
            value = re.sub(r'\s+', ' ', value)
            data[field] = value
    
    # Extract remarks if present
    remarks_patterns = [
        r'Remark part 1\s*\n(.+?)(?=\nRemark part|\nThis code is part|$)',
        r'Remarks\s*\n(.+?)(?=\nIndependent|\nTerritory name|$)',
    ]
    for pattern in remarks_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            remarks = match.group(1).strip()
            remarks = re.sub(r'\s+', ' ', remarks)
            if remarks and len(remarks) > 5:
                data['remarks'] = remarks
                break
    
    # Extract administrative languages
    lang_match = re.search(r'Administrative language.*?alpha-2\s+Administrative language.*?alpha-3\s+Local short name\s*\n([a-z]{2})\s+([a-z]{3})\s+(.+?)(?=\n)', text, re.DOTALL)
    if lang_match:
        data['administrative_language_alpha_2'] = lang_match.group(1)
        data['administrative_language_alpha_3'] = lang_match.group(2)
        data['local_short_name'] = lang_match.group(3).strip()
    
    # Extract subdivisions
    subdivision_pattern = r'(province|state|country|district|special municipality|outlying area|Land|land|region|canton|federal territory)\t([A-Z]{2}-[A-Z0-9]+)\t(.+?)(?=\t|\n)'
    subdivisions = []
    for match in re.finditer(subdivision_pattern, text, re.IGNORECASE):
        subdivisions.append({
            'category': match.group(1),
            'code': match.group(2),
            'name': match.group(3).strip()
        })
    
    if subdivisions:
        data['subdivisions'] = subdivisions[:20]  # Limit to first 20
        data['subdivision_count'] = len(subdivisions)
    
    # Check if we got meaningful data
    if 'alpha_2_code' in data or 'short_name' in data:
        data['success'] = True
    else:
        data['error'] = 'Could not parse country data from page content.'
    
    return data


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the ISO country code skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_country')
            - country_code: Two-letter ISO 3166-1 alpha-2 country code (for 'get_country')

    
    Returns:
        Dictionary containing the requested country code information
    """
    function = params.get('function', '')
    
    if function == 'get_country':
        country_code = params.get('country_code', '')
        if not country_code:
            return {
                'success': False,
                'error': 'country_code parameter is required for get_country function'
            }
        
        return await _extract_country_data(country_code)
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_country'
        }