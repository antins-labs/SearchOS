"""
Autohome Vehicle Configuration Extractor

Extracts detailed vehicle specifications and configurations from car.autohome.com.cn
"""

import re
import json
import aiohttp
from typing import Any, Dict, List, Optional
from html.parser import HTMLParser


class HTMLTagRemover(HTMLParser):
    """Remove HTML tags from text"""
    def __init__(self):
        super().__init__()
        self.text = ""
        
    def handle_data(self, data):
        self.text += data
        
    def get_text(self):
        return self.text.strip()


def remove_html_tags(text: str) -> str:
    """Remove HTML tags from text and clean whitespace"""
    if not text:
        return ""
    
    # Handle HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def extract_series_id_from_url(url: str) -> Optional[str]:
    """Extract series ID from Autohome URL"""
    match = re.search(r'/series/(\d+)', url)
    return match.group(1) if match else None


def parse_config_data(config_json: Dict) -> Dict[str, Any]:
    """Parse and structure the config (parameters) data"""
    result = {
        'param_types': [],
        'spec_ids': set(),
        'models': []
    }
    
    param_type_items = config_json.get('result', {}).get('paramtypeitems', [])
    
    for param_type in param_type_items:
        type_name = remove_html_tags(param_type.get('name', ''))
        type_data = {
            'name': type_name,
            'items': []
        }
        
        for param_item in param_type.get('paramitems', []):
            item_name = remove_html_tags(param_item.get('name', ''))
            item_id = param_item.get('id')
            display_type = param_item.get('displaytype', 0)
            
            item_data = {
                'name': item_name,
                'id': item_id,
                'display_type': display_type,
                'values': {}
            }
            
            # Process value items
            for value_item in param_item.get('valueitems', []):
                spec_id = value_item.get('specid')
                value = remove_html_tags(value_item.get('value', ''))
                sublist = value_item.get('sublist', [])
                
                if spec_id:
                    # Convert to string for consistency
                    spec_id_str = str(spec_id)
                    result['spec_ids'].add(spec_id_str)
                    item_data['values'][spec_id_str] = {
                        'value': value,
                        'sublist': sublist,
                        'price': value_item.get('price', [])
                    }
            
            type_data['items'].append(item_data)
        
        result['param_types'].append(type_data)
    
    # Extract model names from first param type (车型)
    if result['param_types'] and result['param_types'][0]['items']:
        first_item = result['param_types'][0]['items'][0]
        result['models'] = [
            {'spec_id': spec_id, 'name': val['value']}
            for spec_id, val in first_item['values'].items()
        ]
    
    result['spec_ids'] = sorted(list(result['spec_ids']))
    return result


def parse_option_data(option_json: Dict) -> Dict[str, Any]:
    """Parse and structure the option (configurations) data"""
    result = {
        'config_types': [],
        'spec_ids': set()
    }
    
    config_type_items = option_json.get('result', {}).get('configtypeitems', [])
    
    for config_type in config_type_items:
        type_name = remove_html_tags(config_type.get('name', ''))
        type_data = {
            'name': type_name,
            'items': []
        }
        
        for config_item in config_type.get('configitems', []):
            item_name = remove_html_tags(config_item.get('name', ''))
            config_id = config_item.get('configid')
            item_id = config_item.get('id')
            pnid = config_item.get('pnid', '')
            
            item_data = {
                'name': item_name,
                'config_id': config_id,
                'id': item_id,
                'pnid': pnid,
                'values': {}
            }
            
            # Process value items
            for value_item in config_item.get('valueitems', []):
                spec_id = value_item.get('specid')
                value = remove_html_tags(value_item.get('value', ''))
                sublist = value_item.get('sublist', [])
                price = value_item.get('price', [])
                
                if spec_id:
                    # Convert to string for consistency
                    spec_id_str = str(spec_id)
                    result['spec_ids'].add(spec_id_str)
                    item_data['values'][spec_id_str] = {
                        'value': value,
                        'sublist': sublist,
                        'price': price
                    }
            
            type_data['items'].append(item_data)
        
        result['config_types'].append(type_data)
    
    result['spec_ids'] = sorted(list(result['spec_ids']))
    return result


async def fetch_vehicle_config(
    url: str,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Fetch and extract vehicle configuration data from Autohome
    
    Args:
        url: The Autohome config URL (e.g., https://car.autohome.com.cn/config/series/7806.html)
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary containing structured configuration data
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status != 200:
                    return {
                        'error': f'HTTP_{response.status}',
                        'message': f'Failed to fetch page: {url}'
                    }
                
                html = await response.text()
                
                # Extract config variable
                config_match = re.search(r'var config\s*=\s*(\{.+?\});', html, re.DOTALL)
                if not config_match:
                    return {
                        'error': 'config_not_found',
                        'message': 'Configuration data not found in page'
                    }
                
                # Extract option variable
                option_match = re.search(r'var option\s*=\s*(\{.+?\});', html, re.DOTALL)
                
                # Parse JSON data
                try:
                    config_json = json.loads(config_match.group(1))
                except json.JSONDecodeError as e:
                    return {
                        'error': 'config_parse_error',
                        'message': f'Failed to parse config JSON: {str(e)}'
                    }
                
                option_json = None
                if option_match:
                    try:
                        option_json = json.loads(option_match.group(1))
                    except json.JSONDecodeError:
                        pass  # Option data is optional
                
                # Parse and structure the data
                config_data = parse_config_data(config_json)
                
                result = {
                    'success': True,
                    'url': url,
                    'series_id': extract_series_id_from_url(url),
                    'model_count': len(config_data['models']),
                    'models': config_data['models'],
                    'spec_ids': config_data['spec_ids'],
                    'parameters': config_data['param_types'],
                }
                
                if option_json:
                    option_data = parse_option_data(option_json)
                    result['configurations'] = option_data['config_types']
                    # Merge spec_ids
                    all_spec_ids = set(result['spec_ids']) | set(option_data['spec_ids'])
                    result['spec_ids'] = sorted(list(all_spec_ids))
                
                # Add summary statistics
                result['summary'] = {
                    'parameter_categories': len(config_data['param_types']),
                    'total_parameters': sum(len(pt['items']) for pt in config_data['param_types']),
                    'configuration_categories': len(result.get('configurations', [])),
                    'total_configurations': sum(len(ct['items']) for ct in result.get('configurations', [])),
                }
                
                return result
                
        except aiohttp.ClientError as e:
            return {
                'error': 'network_error',
                'message': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'error': 'unexpected_error',
                'message': f'Unexpected error: {str(e)}'
            }


async def fetch_multiple_series(
    series_ids: List[str],
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Fetch configuration data for multiple vehicle series
    
    Args:
        series_ids: List of series IDs
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary containing results for all series
    """
    results = []
    
    for series_id in series_ids:
        url = f"https://car.autohome.com.cn/config/series/{series_id}.html"
        result = await fetch_vehicle_config(url, timeout)
        result['series_id'] = series_id
        results.append(result)
    
    return {
        'success': True,
        'total_series': len(series_ids),
        'results': results
    }


def get_parameter_comparison(
    config_data: Dict[str, Any],
    spec_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a comparison table for specified specifications
    
    Args:
        config_data: Configuration data from fetch_vehicle_config
        spec_ids: List of spec IDs to compare (if None, compares all)
    
    Returns:
        Comparison table data
    """
    if not config_data.get('success'):
        return {'error': 'invalid_config_data', 'message': 'Invalid configuration data provided'}
    
    # Normalize spec_ids to strings
    if spec_ids is None:
        spec_ids = config_data.get('spec_ids', [])
    else:
        spec_ids = [str(sid) for sid in spec_ids]
    
    comparison = {
        'models': [],
        'parameters': []
    }
    
    # Get models
    models = config_data.get('models', [])
    comparison['models'] = [m for m in models if str(m['spec_id']) in spec_ids]
    
    # Build parameter comparison table
    for param_type in config_data.get('parameters', []):
        for item in param_type['items']:
            param_row = {
                'category': param_type['name'],
                'parameter': item['name'],
                'values': {}
            }
            
            for spec_id in spec_ids:
                if spec_id in item['values']:
                    param_row['values'][spec_id] = item['values'][spec_id]['value']
            
            comparison['parameters'].append(param_row)
    
    return comparison


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Autohome vehicle configuration extractor
    
    Args:
        params: Dictionary containing function parameters
        ctx: Optional context (not used)
    
    Returns:
        Dictionary containing the results
    
    Functions:
        - get_config: Get configuration for a single vehicle series
          params: {url: str} or {series_id: str}
        
        - get_multiple: Get configurations for multiple series
          params: {series_ids: List[str]}
        
        - compare: Get comparison table for a series
          params: {url: str, spec_ids: Optional[List[str]]}
    """
    function = params.get('function', 'get_config')
    
    if function == 'get_config':
        # Get single series configuration
        url = params.get('url')
        series_id = params.get('series_id')
        
        if not url and not series_id:
            return {
                'error': 'missing_parameter',
                'message': 'Either url or series_id is required'
            }
        
        if not url:
            url = f"https://car.autohome.com.cn/config/series/{series_id}.html"
        
        return await fetch_vehicle_config(url, params.get('timeout', 30))
    
    elif function == 'get_multiple':
        # Get multiple series configurations
        series_ids = params.get('series_ids', [])
        
        if not series_ids:
            return {
                'error': 'missing_parameter',
                'message': 'series_ids list is required'
            }
        
        return await fetch_multiple_series(series_ids, params.get('timeout', 30))
    
    elif function == 'compare':
        # Get comparison table
        url = params.get('url')
        series_id = params.get('series_id')
        spec_ids = params.get('spec_ids')
        
        if not url and not series_id:
            return {
                'error': 'missing_parameter',
                'message': 'Either url or series_id is required'
            }
        
        if not url:
            url = f"https://car.autohome.com.cn/config/series/{series_id}.html"
        
        config_data = await fetch_vehicle_config(url, params.get('timeout', 30))
        
        if not config_data.get('success'):
            return config_data
        
        return get_parameter_comparison(config_data, spec_ids)
    
    else:
        return {
            'error': 'invalid_function',
            'message': f'Unknown function: {function}. Supported: get_config, get_multiple, compare'
        }


# Export main functions
__all__ = ['execute', 'fetch_vehicle_config', 'fetch_multiple_series', 'get_parameter_comparison']