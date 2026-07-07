"""
Kia Vehicle Specs Extractor

Fetches vehicle specifications and trim comparison data from kia.com.
Supports both individual trim specs and full trim comparison pages.
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, Browser, Page


async def fetch_page_content(url: str, browser: Browser) -> str:
    """Fetch page content with scrolling to load all specs."""
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(3)
        
        # Scroll to load all lazy-loaded content
        for _ in range(15):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(0.2)
        
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(2)
        
        # Get the main content area
        text = await page.evaluate('''() => {
            const main = document.querySelector('.specs-compare-v2-template') ||
                        document.querySelector('.specs-template') ||
                        document.querySelector('.specs-compare') ||
                        document.querySelector('main') ||
                        document.body;
            return main.innerText;
        }''')
        
        return text
    finally:
        await page.close()


def parse_specs_page(text: str) -> dict:
    """Parse individual trim specs page."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    result = {
        'success': True,
        'type': 'specs',
        'model': None,
        'year': None,
        'trim': None,
        'msrp': None,
        'categories': {}
    }
    
    # Extract model/year/trim from header
    # Pattern: "2025 K4 LX" or similar
    for i, line in enumerate(lines[:30]):
        match = re.match(r'(\d{4})\s+([A-Z0-9]+)\s+(.+?)\s*$', line)
        if match:
            result['year'] = match.group(1)
            result['model'] = match.group(2)
            result['trim'] = match.group(3).strip()
            break
    
    # Find MSRP
    for line in lines[:30]:
        msrp_match = re.search(r'\$([\d,]+)\s*Starting\s*MSRP', line, re.IGNORECASE)
        if msrp_match:
            result['msrp'] = msrp_match.group(1).replace(',', '')
            break
    
    # Parse categories
    current_category = None
    current_items = []
    
    category_keywords = [
        'Highlights', 'Colors', 'EPA Mileage Ratings', 'Driver Assistance Technology',
        'Active / Passive Safety', 'Seating Capacity', 'Convenience Features',
        'Climate Control', 'Warranty', 'Interior Features', 'Engine',
        'Infotainment', 'Exterior Features', 'Technical Specifications',
        'Mechanical', 'Measurements', 'Disclaimers'
    ]
    
    for line in lines:
        # Check if this is a category header
        if any(line.lower().startswith(kw.lower()) or line == kw for kw in category_keywords):
            if current_category and current_items:
                result['categories'][current_category] = current_items
            current_category = line
            current_items = []
        elif current_category:
            # Skip navigation items and UI elements
            if line not in ['Back', 'Compare Trims', 'Build Yours', 'Previous', 'Next']:
                if len(line) > 3 and not line.startswith('Menu'):
                    current_items.append(line)
    
    if current_category and current_items:
        result['categories'][current_category] = current_items
    
    return result


def parse_compare_page(text: str) -> dict:
    """Parse trim comparison page."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    result = {
        'success': True,
        'type': 'compare',
        'model': None,
        'year': None,
        'trims': [],
        'specifications': {}
    }
    
    # Extract model and year
    for line in lines[:20]:
        match = re.match(r'(\d{4})\s+([A-Z0-9]+)', line)
        if match:
            result['year'] = match.group(1)
            result['model'] = match.group(2)
            break
    
    # Find trim names and prices
    # Pattern: "LX", "$22,290 Starting MSRP*"
    trim_pattern = re.compile(r'^(LX|LXS|EX|GT-Line|GT-Line Turbo|S|SX|SX Prestige|LX-P|EX-P|[A-Z][A-Za-z0-9\s\-]+)$')
    msrp_pattern = re.compile(r'\$([\d,]+)\s*Starting\s*MSRP', re.IGNORECASE)
    
    i = 0
    trim_list = []
    while i < len(lines[:50]):
        line = lines[i]
        # Check for trim name
        if trim_pattern.match(line) and line not in ['Build Yours', 'Edit Trims', 'Remove']:
            trim_name = line
            # Look for MSRP in next few lines
            j = i + 1
            while j < min(i + 5, len(lines)):
                msrp_match = msrp_pattern.search(lines[j])
                if msrp_match:
                    price = msrp_match.group(1).replace(',', '')
                    trim_list.append({'name': trim_name, 'msrp': price})
                    i = j
                    break
                j += 1
        i += 1
    
    result['trims'] = trim_list
    
    # Build trim order for mapping values
    trim_names = [t['name'] for t in trim_list]
    num_trims = len(trim_names)
    
    if num_trims == 0:
        num_trims = 5  # Default assumption
        trim_names = ['LX', 'LXS', 'EX', 'GT-Line', 'GT-Line Turbo']
    
    # Parse categories and specifications
    category_keywords = [
        'Top Features', 'Colors', 'Exterior Colors', 'Interior Colors',
        'EPA Mileage Ratings', 'Driver Assistance Technology',
        'Active / Passive Safety', 'Seating Capacity', 'Convenience Features',
        'Climate Control', 'Warranty', 'Interior Features',
        'Infotainment & Connected Car Technologies', 'Exterior Features',
        'Technical Specifications', 'Engine Type', 'Measurements'
    ]
    
    current_category = None
    current_specs = {}
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for category
        is_category = False
        for kw in category_keywords:
            if line.lower() == kw.lower() or line.startswith(kw):
                if current_category and current_specs:
                    result['specifications'][current_category] = current_specs
                current_category = line
                current_specs = {}
                is_category = True
                break
        
        if is_category:
            i += 1
            continue
        
        # If we're in a category, try to parse spec items
        if current_category:
            # Skip UI elements
            if line in ['Standard', 'Not Available', 'Available', 'Build Yours', 'Remove', 'Edit Trims']:
                i += 1
                continue
            
            # Skip trim names in spec rows
            if line in trim_names:
                i += 1
                continue
            
            # Skip color code patterns like "lx - Exterior -"
            if re.match(r'^[a-z]+-\s*(Exterior|Interior)\s*-$', line, re.IGNORECASE):
                i += 1
                continue
            
            # Skip small snippet lines
            if len(line) < 3:
                i += 1
                continue
            
            # Check if next lines contain values (Standard/Not Available/Available/actual values)
            # This is a spec item with values for each trim
            values = []
            j = i + 1
            value_count = 0
            
            # Collect values
            while j < len(lines) and value_count < num_trims:
                next_line = lines[j]
                if next_line in ['Standard', 'Not Available', 'Available']:
                    values.append(next_line)
                    value_count += 1
                    j += 1
                elif re.match(r'^[\d.,/]+\s*(in\.|cu\. ft\.|gal\.|lb\.|hp|lb\.-ft\.|cc|:1)?$', next_line):
                    values.append(next_line)
                    value_count += 1
                    j += 1
                elif next_line in trim_names:
                    break
                elif any(next_line.lower().startswith(kw.lower()) for kw in category_keywords):
                    break
                else:
                    # Could be a value like "Turbocharged 1.6 liter 4-Cylinder"
                    if len(next_line) > 3 and not next_line.startswith('$'):
                        # Check if it looks like a spec value
                        if value_count < num_trims:
                            values.append(next_line)
                            value_count += 1
                            j += 1
                        else:
                            break
                    else:
                        break
            
            if values:
                current_specs[line] = values[:num_trims]  # Limit to number of trims
                i = j
            else:
                i += 1
        else:
            i += 1
    
    if current_category and current_specs:
        result['specifications'][current_category] = current_specs
    
    return result


def build_url(model: str, year: int = None, trim: str = None, compare: bool = False) -> str:
    """Build Kia URL for specs or compare page."""
    model_lower = model.lower().replace(' ', '')
    
    if compare:
        # e.g., https://www.kia.com/us/en/k4/specs-compare
        return f"https://www.kia.com/us/en/{model_lower}/specs-compare"
    else:
        # e.g., https://www.kia.com/us/en/vehicles/k4/2025/specs
        year_str = str(year) if year else '2025'
        return f"https://www.kia.com/us/en/vehicles/{model_lower}/{year_str}/specs"


async def get_vehicle_specs(model: str, year: int = None, trim: str = None) -> dict:
    """Get specs for a specific vehicle model and optionally trim."""
    url = build_url(model, year, trim, compare=False)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            text = await fetch_page_content(url, browser)
            return parse_specs_page(text)
        except Exception as e:
            return {'success': False, 'error': str(e), 'url': url}
        finally:
            await browser.close()


async def get_trim_comparison(model: str) -> dict:
    """Get trim comparison for a vehicle model."""
    url = build_url(model, compare=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            text = await fetch_page_content(url, browser)
            return parse_compare_page(text)
        except Exception as e:
            return {'success': False, 'error': str(e), 'url': url}
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main executor function for Kia vehicle specs extraction.
    
    Args:
        params: Dict with 'function' and function-specific parameters
        ctx: Context (unused)
    
    Returns:
        Dict with extraction results
    """
    function = params.get('function', '')
    
    if function == 'get_trim_comparison':
        model = params.get('model', '').strip()
        if not model:
            return {'success': False, 'error': 'model parameter is required'}
        
        result = await get_trim_comparison(model)
        return result
    
    elif function == 'get_vehicle_specs':
        model = params.get('model', '').strip()
        if not model:
            return {'success': False, 'error': 'model parameter is required'}
        
        year = params.get('year')
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                return {'success': False, 'error': 'year must be an integer'}
        
        trim = params.get('trim', '').strip() if params.get('trim') else None
        
        result = await get_vehicle_specs(model, year, trim)
        return result
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: get_trim_comparison, get_vehicle_specs'
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        if len(sys.argv) > 1:
            func = sys.argv[1]
            if func == 'compare':
                model = sys.argv[2] if len(sys.argv) > 2 else 'k4'
                result = await get_trim_comparison(model)
            elif func == 'specs':
                model = sys.argv[2] if len(sys.argv) > 2 else 'k4'
                year = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
                result = await get_vehicle_specs(model, year)
        else:
            print("Testing trim comparison for K4...")
            result = await get_trim_comparison('k4')
        
        import json
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())