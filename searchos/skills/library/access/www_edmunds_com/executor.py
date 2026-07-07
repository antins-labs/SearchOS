"""
Edmunds.com Vehicle Data Access Skill

This skill fetches vehicle specifications and trim data from Edmunds.com.
The site has strong anti-bot protections, so this skill uses Playwright with
appropriate techniques to access the data.

Target URLs:
- https://www.edmunds.com/{make}/{model}/{year}/features-specs/
- https://www.edmunds.com/{make}/{model}/{year}/trims/

Data extracted:
- Vehicle specifications (engine, transmission, dimensions, etc.)
- Trim levels and their differences
- Feature availability by trim
- Pricing information
"""

import asyncio
import json
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext


class EdmundsAccess:
    """Handles access to Edmunds.com vehicle data."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def setup(self):
        """Initialize the browser with appropriate settings."""
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            viewport={'width': 1920, 'height': 1080},
            screen={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/Los_Angeles',
            has_touch=False,
            is_mobile=False,
            java_script_enabled=True,
        )
        
        # Add anti-detection scripts
        await self.context.add_cookies([
            {
                'name': 'OptanonAlertBoxClosed',
                'value': '2024-01-01T00:00:00.000Z',
                'domain': '.edmunds.com',
                'path': '/'
            },
            {
                'name': 'privacy相关政策',
                'value': '1',
                'domain': '.edmunds.com',
                'path': '/'
            }
        ])
        
        self.page = await self.context.new_page()
        
        # Inject stealth scripts
        await self.page.add_init_script('''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = { runtime: {} };
        ''')
    
    async def close(self):
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
    
    async def fetch_page(self, make: str, model: str, year: str, page_type: str = "features-specs") -> dict:
        """
        Fetch vehicle data from Edmunds.
        
        Args:
            make: Vehicle make (e.g., 'nissan', 'buick', 'lexus')
            model: Vehicle model (e.g., 'sentra', 'envision', 'nx')
            year: Model year (e.g., '2025')
            page_type: Type of page - 'features-specs' or 'trims'
        
        Returns:
            Dictionary with vehicle data or error information
        """
        if not self.page:
            await self.setup()
        
        # Construct URL
        url = f"https://www.edmunds.com/{make.lower()}/{model.lower()}/{year}/{page_type}/"
        
        result = {
            'source': 'edmunds',
            'url': url,
            'make': make,
            'model': model,
            'year': year,
            'page_type': page_type,
            'success': False,
            'blocked': False,
            'data': None,
            'error': None
        }
        
        try:
            # Navigate to the page
            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            if response is None:
                result['error'] = 'No response received'
                return result
            
            result['status_code'] = response.status
            
            if response.status == 403:
                result['blocked'] = True
                result['error'] = 'Access blocked by Edmunds (403 Forbidden)'
                return result
            
            if response.status != 200:
                result['error'] = f'HTTP error {response.status}'
                return result
            
            # Wait for page to load
            await asyncio.sleep(3)
            
            # Check for access denied page
            content = await self.page.content()
            if 'access denied' in content.lower() or '403' in content.lower():
                result['blocked'] = True
                result['error'] = 'Access blocked by Edmunds (403 page content)'
                return result
            
            # Extract __NEXT_DATA__ which contains all the page data
            next_data = await self.page.query_selector('script#__NEXT_DATA__')
            
            if next_data:
                data_script = await next_data.inner_text()
                page_data = json.loads(data_script)
                
                # Extract relevant data
                props = page_data.get('props', {}).get('pageProps', {})
                
                # Parse vehicle data
                vehicle_data = self._parse_vehicle_data(props, make, model, year)
                
                result['success'] = True
                result['data'] = vehicle_data
                result['raw_props_keys'] = list(props.keys())
            else:
                # Try extracting from page content
                vehicle_data = await self._extract_from_page(make, model, year)
                
                if vehicle_data:
                    result['success'] = True
                    result['data'] = vehicle_data
                else:
                    result['error'] = 'Could not extract vehicle data from page'
            
        except Exception as e:
            result['error'] = f"Error fetching page: {str(e)}"
        
        return result
    
    def _parse_vehicle_data(self, props: dict, make: str, model: str, year: str) -> dict:
        """Parse vehicle data from the __NEXT_DATA__ props."""
        data = {
            'make': make.title(),
            'model': model.title(),
            'year': year,
            'trims': [],
            'specifications': {},
            'features': {},
            'pricing': {}
        }
        
        # Look for common data structures
        # Edmunds typically stores trim data in various locations
        
        # Try to find vehicle/trims data
        for key in ['vehicle', 'trims', 'styles', 'modelYear', 'vehicleInfo']:
            if key in props:
                val = props[key]
                if isinstance(val, dict):
                    data['trims'] = self._extract_trims(val)
                elif isinstance(val, list):
                    data['trims'] = [self._normalize_trim(t) for t in val]
        
        # Look for specifications
        for key in ['specs', 'specifications', 'technicalSpecs']:
            if key in props:
                data['specifications'] = props[key]
        
        # Look for features
        for key in ['features', 'equipment', 'standardFeatures']:
            if key in props:
                data['features'] = props[key]
        
        # Look for pricing
        for key in ['pricing', 'prices', 'msrp']:
            if key in props:
                data['pricing'] = props[key]
        
        # Recursively search for trim-like data
        if not data['trims']:
            data['trims'] = self._find_trims_recursive(props)
        
        return data
    
    def _extract_trims(self, data: dict) -> list:
        """Extract trim information from a data dict."""
        trims = []
        
        # Common keys for trim lists
        trim_keys = ['trims', 'styles', 'models', 'trimLevels', 'styleList']
        
        for key in trim_keys:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    trims.append(self._normalize_trim(item))
        
        return trims
    
    def _normalize_trim(self, data: dict) -> dict:
        """Normalize trim data to a consistent format."""
        trim = {}
        
        # Common identifiers
        for key in ['id', 'styleId', 'trimId', 'modelId']:
            if key in data:
                trim['id'] = data[key]
                break
        
        # Trim name
        for key in ['name', 'trimName', 'styleName', 'trim', 'modelName']:
            if key in data and data[key]:
                trim['name'] = data[key]
                break
        
        # Pricing
        for key in ['msrp', 'price', 'baseMSRP', 'invoice', 'startingPrice']:
            if key in data:
                trim['msrp'] = data[key]
                break
        
        # Copy other relevant fields
        for key in ['engine', 'transmission', 'drivetrain', 'bodyStyle', 'fuelType']:
            if key in data:
                trim[key] = data[key]
        
        return trim
    
    def _find_trims_recursive(self, data: Any, depth: int = 0, max_depth: int = 5) -> list:
        """Recursively search for trim data."""
        if depth > max_depth:
            return []
        
        trims = []
        
        if isinstance(data, dict):
            # Check if this looks like a trim object
            trim_indicators = ['trimName', 'styleName', 'msrp', 'baseMSRP', 'trimId']
            if any(k in data for k in trim_indicators):
                trims.append(self._normalize_trim(data))
            
            # Also check for arrays of trims
            for key in ['trims', 'styles', 'trimLevels', 'models']:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, dict):
                            trims.append(self._normalize_trim(item))
            
            # Recurse into values
            for v in data.values():
                trims.extend(self._find_trims_recursive(v, depth + 1, max_depth))
        
        elif isinstance(data, list):
            for item in data:
                trims.extend(self._find_trims_recursive(item, depth + 1, max_depth))
        
        return trims
    
    async def _extract_from_page(self, make: str, model: str, year: str) -> Optional[dict]:
        """Extract data from page elements if __NEXT_DATA__ is not available."""
        data = {
            'make': make.title(),
            'model': model.title(),
            'year': year,
            'trims': [],
            'specifications': {},
            'features': {},
            'pricing': {}
        }
        
        try:
            # Try to extract trim names from page elements
            trim_elements = await self.page.query_selector_all('[class*="trim"], [class*="style"], [data-trim]')
            
            for elem in trim_elements[:20]:  # Limit to first 20
                text = await elem.inner_text()
                if text and len(text) < 100:
                    data['trims'].append({'name': text.strip()})
            
            # Try to extract pricing
            price_elements = await self.page.query_selector_all('[class*="price"], [class*="msrp"]')
            for elem in price_elements[:10]:
                text = await elem.inner_text()
                if '$' in text:
                    # Extract price
                    price_match = re.search(r'\$[\d,]+', text)
                    if price_match:
                        data['pricing']['found'] = price_match.group()
            
            # Try to extract specs from tables
            spec_tables = await self.page.query_selector_all('table')
            for table in spec_tables[:5]:
                rows = await table.query_selector_all('tr')
                for row in rows:
                    cells = await row.query_selector_all('td, th')
                    if len(cells) >= 2:
                        key = await cells[0].inner_text()
                        value = await cells[1].inner_text()
                        if key and value:
                            data['specifications'][key.strip()] = value.strip()
            
            return data if data['trims'] or data['specifications'] else None
            
        except Exception as e:
            return None


# Global instance for reuse
_access: Optional[EdmundsAccess] = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main execution function for the Edmunds skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_features_specs', 'get_trims', 'get_vehicle_data'
            - make: Vehicle make (e.g., 'nissan', 'buick', 'lexus')
            - model: Vehicle model (e.g., 'sentra', 'envision', 'nx')
            - year: Model year (e.g., '2025')
    
    Returns:
        Dictionary with vehicle data or error information
    """
    global _access
    
    function = params.get('function', 'get_vehicle_data')
    make = params.get('make', '').lower().strip()
    model = params.get('model', '').lower().strip()
    year = params.get('year', '').strip()
    
    # Validate inputs
    if not make:
        return {
            'success': False,
            'error': 'Missing required parameter: make',
            'data': None
        }
    
    if not model:
        return {
            'success': False,
            'error': 'Missing required parameter: model',
            'data': None
        }
    
    if not year:
        return {
            'success': False,
            'error': 'Missing required parameter: year',
            'data': None
        }
    
    # Map function to page type
    function_map = {
        'get_features_specs': 'features-specs',
        'get_trims': 'trims',
        'get_vehicle_data': 'features-specs',  # Default to specs
    }
    
    page_type = function_map.get(function, 'features-specs')
    
    try:
        # Initialize or reuse access
        if _access is None:
            _access = EdmundsAccess()
            await _access.setup()
        
        # Fetch the data
        result = await _access.fetch_page(make, model, year, page_type)
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Execution error: {str(e)}',
            'data': None,
            'make': make,
            'model': model,
            'year': year
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test with the provided URLs from the probe list
        test_cases = [
            {'make': 'nissan', 'model': 'sentra', 'year': '2025', 'function': 'get_features_specs'},
            {'make': 'buick', 'model': 'envision', 'year': '2025', 'function': 'get_trims'},
            {'make': 'lexus', 'model': 'nx', 'year': '2025', 'function': 'get_trims'},
        ]
        
        global _access
        
        for test in test_cases:
            print(f"\n{'='*60}")
            print(f"Testing: {test['year']} {test['make']} {test['model']} - {test['function']}")
            print('='*60)
            
            result = await execute(test)
            print(f"Success: {result.get('success')}")
            print(f"Blocked: {result.get('blocked')}")
            print(f"Error: {result.get('error')}")
            
            if result.get('data'):
                data = result['data']
                print(f"Trims found: {len(data.get('trims', []))}")
                if data.get('trims'):
                    for trim in data['trims'][:5]:
                        print(f"  - {trim.get('name', 'Unknown')}")
                print(f"Specs: {list(data.get('specifications', {}).keys())[:5]}")
            
            await asyncio.sleep(2)
        
        # Cleanup
        if _access:
            await _access.close()
    
    asyncio.run(test())