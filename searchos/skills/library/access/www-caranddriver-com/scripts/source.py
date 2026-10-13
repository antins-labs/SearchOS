"""
Car and Driver vehicle data extractor.
Extracts specs, pricing, ratings, and trim data from carandriver.com vehicle pages.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional
import urllib.parse


async def fetch_page(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def parse_next_data(html: str) -> Optional[dict]:
    """Extract __NEXT_DATA__ JSON from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    next_data_script = soup.find('script', id='__NEXT_DATA__')
    if next_data_script and next_data_script.string:
        try:
            return json.loads(next_data_script.string)
        except json.JSONDecodeError:
            pass
    return None


def extract_json_ld(html: str) -> list[dict]:
    """Extract JSON-LD structured data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    results = []
    for script in json_ld_scripts:
        if script.string:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except json.JSONDecodeError:
                pass
    return results


def parse_year_data(year_obj: dict) -> dict:
    """Parse a year object from vehicle_models."""
    result = {
        'year': year_obj.get('year'),
        'market_status': year_obj.get('market_status'),
        'state': year_obj.get('state'),
    }
    
    # Specs
    specs = year_obj.get('specs', {})
    if specs:
        result['specs'] = {
            'epa': specs.get('epa'),
            'seating': specs.get('seating'),
            'cargo_capacity': specs.get('cargo_capacity'),
            'drivetrains': specs.get('drivetrains'),
            'warranties': specs.get('warranties'),
        }
    
    # Price
    price = year_obj.get('price', {})
    if price:
        result['price'] = {
            'low': price.get('low'),
            'high': price.get('high'),
            'is_estimate': price.get('is_estimate'),
        }
    
    # Ratings
    ratings = year_obj.get('ratings', {})
    if ratings:
        result['ratings'] = {
            'cd_rating': ratings.get('cd_rating'),
            'max_rating': ratings.get('max_rating'),
            'safety': ratings.get('safety', {}).get('high') if ratings.get('safety') else None,
            'is_cd_ten_best': ratings.get('is_cd_ten_best'),
            'is_cd_editors_choice': ratings.get('is_cd_editors_choice'),
            'is_cd_ev_of_the_year': ratings.get('is_cd_ev_of_the_year'),
        }
    
    # Trims
    chrome_trims = year_obj.get('chrome_trims', [])
    if chrome_trims:
        result['trims'] = [{
            'name': trim.get('name'),
            'msrp': trim.get('msrp'),
            'body_style': trim.get('body_style'),
            'drivetrain': trim.get('drivetrain'),
            'engine': trim.get('engine'),
            'transmission': trim.get('transmission'),
            'fuel_type': trim.get('fuel_type'),
            'mpg_city': trim.get('mpg_city'),
            'mpg_highway': trim.get('mpg_highway'),
            'seating_capacity': trim.get('seating_capacity'),
            'horsepower': trim.get('horsepower'),
            'torque': trim.get('torque'),
        } for trim in chrome_trims]
    
    return result


def parse_vehicle_model(vm: dict, target_year: Optional[int] = None) -> dict:
    """Parse vehicle model data."""
    result = {
        'id': vm.get('id'),
        'name': vm.get('name'),
        'make': vm.get('make', {}).get('name') if vm.get('make') else None,
        'primary_year': vm.get('primary_year'),
        'body_style': vm.get('primary_body_style'),
    }
    
    # Price
    price = vm.get('price', {})
    if price:
        result['price'] = {
            'low': price.get('low'),
            'high': price.get('high'),
            'is_estimate': price.get('is_estimate'),
        }
    
    # Ratings
    ratings = vm.get('ratings', {})
    if ratings:
        result['ratings'] = {
            'cd_rating': ratings.get('cd_rating'),
            'max_rating': ratings.get('max_rating'),
            'is_cd_ten_best': ratings.get('is_cd_ten_best'),
            'is_cd_editors_choice': ratings.get('is_cd_editors_choice'),
            'is_cd_ev_of_the_year': ratings.get('is_cd_ev_of_the_year'),
        }
    
    # Properties (engine, performance)
    properties = vm.get('properties', {})
    if properties:
        result['properties'] = {
            'fuel_types': properties.get('fuel_types'),
            'primary_fuel_type': properties.get('primary_fuel_type'),
            'top_speed': properties.get('topspeed'),
            'engine_liters': properties.get('liters'),
            'horsepower': properties.get('horsepower'),
            'zero_to_sixty': properties.get('zerosixty'),
            'epa_highway': properties.get('epa_highway'),
            'epa_city': properties.get('epa_city'),
            'epa_highway_elec': properties.get('epa_highway_elec'),
            'epa_city_elec': properties.get('epa_city_elec'),
        }
    
    # Years - filter if target_year specified
    years = vm.get('years', [])
    years_data = []
    for y in years:
        year = y.get('year')
        if year:
            if target_year is None or year == target_year:
                year_data = parse_year_data(y)
                if year_data:
                    years_data.append(year_data)
    
    if years_data:
        result['years'] = years_data
        # If single year requested, also put at top level
        if target_year and len(years_data) == 1:
            result['year_data'] = years_data[0]
    
    # Available years list
    if years:
        result['available_years'] = [y.get('year') for y in years if y.get('year')]
    
    # Submodels
    submodels = vm.get('submodels', [])
    if submodels:
        result['submodels'] = [{
            'id': sm.get('id'),
            'name': sm.get('name'),
            'year': sm.get('year'),
        } for sm in submodels]
    
    return result


def parse_vehicle_tags(vt: dict) -> dict:
    """Parse vehicle tags for basic info."""
    return {
        'body_style': vt.get('body_style'),
        'year': vt.get('year'),
        'make': vt.get('make', {}).get('name') if vt.get('make') else None,
        'model': vt.get('model', {}).get('name') if vt.get('model') else None,
        'submodel': vt.get('submodel', {}).get('name') if vt.get('submodel') else None,
        'fuel': vt.get('submodel', {}).get('fuel') if vt.get('submodel') else None,
    }


def parse_alternative_body(html_content: str) -> dict:
    """Parse specs from alternative_body HTML content."""
    result = {'specs_text': html_content}
    
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    
    # Extract price
    price_match = re.search(r'Base/As Tested:\s*\$?([\d,]+)\s*/?\s*\$?([\d,]+)?', text)
    if price_match:
        result['base_price'] = price_match.group(1).replace(',', '')
        if price_match.group(2):
            result['as_tested_price'] = price_match.group(2).replace(',', '')
    
    # Extract horsepower
    hp_match = re.search(r'(\d+)\s*hp', text, re.I)
    if hp_match:
        result['horsepower'] = int(hp_match.group(1))
    
    # Extract torque
    torque_match = re.search(r'(\d+)\s*lb-ft', text, re.I)
    if torque_match:
        result['torque'] = int(torque_match.group(1))
    
    # Extract 0-60 time
    zero_sixty_match = re.search(r'60\s*mph:\s*([\d.]+)\s*sec', text, re.I)
    if zero_sixty_match:
        result['zero_to_sixty'] = float(zero_sixty_match.group(1))
    
    # Extract curb weight
    weight_match = re.search(r'Curb Weight:\s*([\d,]+)\s*lb', text, re.I)
    if weight_match:
        result['curb_weight'] = int(weight_match.group(1).replace(',', ''))
    
    # Extract EPA fuel economy
    epa_match = re.search(r'Combined/City/Highway:\s*(\d+)/(\d+)/(\d+)\s*MPGe?', text, re.I)
    if epa_match:
        result['epa_combined'] = int(epa_match.group(1))
        result['epa_city'] = int(epa_match.group(2))
        result['epa_highway'] = int(epa_match.group(3))
    
    # Extract range
    range_match = re.search(r'Range:\s*(\d+)\s*mi', text, re.I)
    if range_match:
        result['range'] = int(range_match.group(1))
    
    return result


def parse_json_ld_vehicle(json_ld_list: list[dict]) -> Optional[dict]:
    """Extract vehicle data from JSON-LD."""
    for item in json_ld_list:
        if item.get('@type') == 'Vehicle':
            result = {
                'body_type': item.get('bodyType'),
                'make': item.get('brand', {}).get('name') if isinstance(item.get('brand'), dict) else item.get('brand'),
                'model': item.get('model'),
                'year': item.get('productionDate'),
                'description': item.get('description'),
            }
            
            offers = item.get('offers', {})
            if offers:
                result['price'] = {
                    'base': offers.get('price'),
                    'currency': offers.get('priceCurrency'),
                }
                price_spec = offers.get('priceSpecification', {})
                if price_spec:
                    result['price']['min'] = price_spec.get('minPrice')
                    result['price']['max'] = price_spec.get('maxPrice')
            
            review = item.get('review', {})
            if review:
                rating = review.get('reviewRating', {})
                if rating:
                    result['rating'] = {
                        'value': rating.get('ratingValue'),
                        'best': rating.get('bestRating'),
                        'worst': rating.get('worstRating'),
                    }
            
            return result
    return None


async def get_vehicle_data(url: str) -> dict:
    """Fetch and parse vehicle data from a Car and Driver URL."""
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_page(url, session)
        
        if status != 200:
            return {'error': f'HTTP error: {status}', 'url': url}
        
        next_data = parse_next_data(html)
        if not next_data:
            return {'error': 'No __NEXT_DATA__ found', 'url': url}
        
        props = next_data.get('props', {}).get('pageProps', {}).get('data', {})
        content = props.get('content', [])
        
        if not content:
            return {'error': 'No content found in page data', 'url': url}
        
        item = content[0]
        result = {
            'url': url,
            'title': item.get('title'),
            'slug': item.get('slug'),
        }
        
        # Parse vehicle models
        vehicle_models = item.get('vehicle_models', [])
        if vehicle_models:
            result['vehicle'] = parse_vehicle_model(vehicle_models[0])
        
        # Parse vehicle tags
        vehicle_tags = item.get('vehicle_tags', [])
        if vehicle_tags:
            result['tags'] = parse_vehicle_tags(vehicle_tags[0])
        
        # Parse alternative_body (specs page content)
        alternative_body = item.get('alternative_body')
        if alternative_body:
            result['specs_detail'] = parse_alternative_body(alternative_body)
        
        # Get JSON-LD as backup
        json_ld = extract_json_ld(html)
        if json_ld:
            vehicle_json_ld = parse_json_ld_vehicle(json_ld)
            if vehicle_json_ld:
                result['json_ld'] = vehicle_json_ld
        
        return result


async def search_make_model(make: str, model: str, year: Optional[int] = None) -> dict:
    """Search for vehicle by make/model (and optionally year)."""
    # Construct URL
    model_slug = model.lower().replace(' ', '-')
    url = f"https://www.caranddriver.com/{make.lower()}/{model_slug}"
    
    if year:
        url = f"{url}-{year}"
    
    return await get_vehicle_data(url)


async def get_specs_page(make: str, model: str, year: int, submodel: Optional[str] = None) -> dict:
    """Get specs for a specific vehicle year/submodel."""
    # Construct specs URL based on observed patterns
    # Pattern: /ford/mustang-mach-e/specs/2021/ford_mach-e_ford-mach-e_2021
    # The submodel ID in URL uses underscores and lowercase
    
    model_slug = model.lower().replace(' ', '-')
    
    # For submodel ID, we need to construct it properly
    # Common patterns observed:
    # - mustang-mach-e -> mach-e (for submodel part)
    # - ranger -> ranger
    if submodel:
        submodel_slug = submodel.lower().replace(' ', '-')
        # Try different URL patterns
        # Pattern 1: make_model_submodel_year
        id_part = f"{make.lower()}_{model_slug.replace('-', '-')}_{submodel_slug.replace('-', '-')}_{year}".replace('--', '-')
    else:
        # Pattern: make_model-submodel_year or make_model_year
        # e.g., ford_mach-e_ford-mach-e_2021
        # The first part is make_model, second is full model name, last is year
        model_underscore = model.lower().replace(' ', '-')
        id_part = f"{make.lower()}_{model_underscore.replace('-', '-')}_{model_underscore.replace('-', '-')}_{year}"
    
    # Simplified URL construction
    url = f"https://www.caranddriver.com/{make.lower()}/{model_slug}/specs/{year}/{make.lower()}_{model_slug}_{year}"
    
    return await get_vehicle_data(url)


def get_years_available(data: dict) -> list[int]:
    """Get list of available years from vehicle data."""
    if 'vehicle' in data and 'available_years' in data['vehicle']:
        return data['vehicle']['available_years']
    return []


def get_year_data(data: dict, year: int) -> Optional[dict]:
    """Get data for a specific year from vehicle data."""
    if 'vehicle' in data and 'years' in data['vehicle']:
        for y in data['vehicle']['years']:
            if y.get('year') == year:
                return y
    return None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Car and Driver data extraction.
    
    Functions:
    - get_vehicle: Get vehicle data by URL
    - search: Search by make/model/year
    - get_specs: Get specs page by make/model/year/submodel (note: currently returns 404 for some URLs)
    - list_years: List available years for a model
    """
    function = params.get('function')
    
    if function == 'get_vehicle':
        url = params.get('url')
        if not url:
            return {'error': 'Missing required parameter: url'}
        
        return await get_vehicle_data(url)
    
    elif function == 'search':
        make = params.get('make')
        model = params.get('model')
        year = params.get('year')
        
        if not make or not model:
            return {'error': 'Missing required parameters: make, model'}
        
        return await search_make_model(make, model, year)
    
    elif function == 'get_specs':
        make = params.get('make')
        model = params.get('model')
        year = params.get('year')
        submodel = params.get('submodel')
        
        if not make or not model or not year:
            return {'error': 'Missing required parameters: make, model, year'}
        
        # Note: get_specs_page currently has URL construction issues
        # Instead, search for the vehicle and include year-specific data
        result = await search_make_model(make, model, year)
        
        # If we have year data, enhance it
        if 'vehicle' in result and 'years' in result['vehicle']:
            for y in result['vehicle']['years']:
                if y.get('year') == year:
                    result['year_data'] = y
                    break
        
        return result
    
    elif function == 'list_years':
        make = params.get('make')
        model = params.get('model')
        
        if not make or not model:
            return {'error': 'Missing required parameters: make, model'}
        
        data = await search_make_model(make, model)
        if 'error' in data:
            return data
        
        years = get_years_available(data)
        return {
            'make': make,
            'model': model,
            'available_years': years,
            'url': data.get('url'),
        }
    
    else:
        return {'error': f'Unknown function: {function}. Use get_vehicle, search, get_specs, or list_years.'}


# For testing
if __name__ == '__main__':
    async def test():
        # Test search
        print("=== Testing search ===")
        result = await search_make_model('ford', 'ranger', 2019)
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n=== Testing list_years ===")
        result = await execute({'function': 'list_years', 'make': 'ford', 'model': 'bronco'})
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())