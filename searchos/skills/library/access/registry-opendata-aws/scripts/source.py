"""
AWS Open Data Registry Access Skill

Fetches structured dataset metadata from registry.opendata.aws including
description, resources (S3 buckets, ARNs), and related information.
"""

import aiohttp
import json
import re
from html.parser import HTMLParser
from typing import Any


class ResourceParser(HTMLParser):
    """Parse resource list items from AWS Open Data Registry pages"""
    
    def __init__(self):
        super().__init__()
        self.resources = []
        self.current_resource = None
        self.current_key = None
        self.current_value = ""
        self.in_resource_list = False
        self.in_dt = False
        self.in_dd = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'dl' and attrs_dict.get('class') == 'resource-list':
            self.in_resource_list = True
            self.current_resource = {}
        elif tag == 'dt' and self.in_resource_list:
            self.in_dt = True
            self.current_value = ""
        elif tag == 'dd' and self.in_resource_list:
            self.in_dd = True
            self.current_value = ""
            
    def handle_endtag(self, tag):
        if tag == 'dl' and self.in_resource_list:
            if self.current_resource:
                self.resources.append(self.current_resource)
            self.in_resource_list = False
            self.current_resource = None
        elif tag == 'dt' and self.in_dt:
            self.in_dt = False
            key = re.sub(r'\s+', '_', self.current_value.strip().lower())
            key = re.sub(r'[^a-z0-9_]', '', key)
            self.current_key = key
        elif tag == 'dd' and self.in_dd:
            self.in_dd = False
            if self.current_resource is not None and self.current_key:
                value = re.sub(r'<[^>]+>', '', self.current_value.strip())
                self.current_resource[self.current_key] = value
                self.current_key = None
                
    def handle_data(self, data):
        if self.in_dt or self.in_dd:
            self.current_value += data


def extract_dataset_metadata(html: str) -> dict:
    """Extract all metadata from a dataset page"""
    result = {}
    
    # Check for meta refresh redirect
    refresh_match = re.search(
        r'<meta[^>]*http-equiv=["\']?Refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\'>\s]+)',
        html, 
        re.IGNORECASE
    )
    if refresh_match:
        result['redirect'] = refresh_match.group(1)
        return result
    
    # Extract JSON-LD
    json_ld_match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', 
        html, 
        re.DOTALL
    )
    if json_ld_match:
        try:
            result['json_ld'] = json.loads(json_ld_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Extract resources
    parser = ResourceParser()
    parser.feed(html)
    if parser.resources:
        result['resources'] = parser.resources
    
    # Extract title
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        title = title_match.group(1).strip()
        if " - Registry of Open Data on AWS" in title:
            title = title.replace(" - Registry of Open Data on AWS", "")
        result['title'] = title
    
    return result


def normalize_dataset_path(path: str) -> str:
    """Normalize a dataset path to a full URL"""
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if path.startswith('/'):
        return f"https://registry.opendata.aws{path}"
    return f"https://registry.opendata.aws/{path}/"


async def fetch_dataset(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch a dataset page and follow meta refresh redirects"""
    seen_urls = set()
    current_url = url
    max_redirects = 5
    
    for _ in range(max_redirects):
        if current_url in seen_urls:
            break
        seen_urls.add(current_url)
        
        try:
            async with session.get(current_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return {
                        'error': f'HTTP {response.status}',
                        'url': current_url
                    }
                
                html = await response.text()
                data = extract_dataset_metadata(html)
                
                if 'redirect' in data:
                    redirect_url = data['redirect']
                    if redirect_url.startswith('/'):
                        redirect_url = f"https://registry.opendata.aws{redirect_url}"
                    current_url = redirect_url
                    continue
                
                data['url'] = current_url
                return data
                
        except aiohttp.ClientError as e:
            return {
                'error': str(e),
                'url': current_url
            }
    
    return {'error': 'Too many redirects', 'url': current_url}


async def get_dataset(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch metadata for a single dataset"""
    dataset_path = params.get('dataset_path', '')
    if not dataset_path:
        return {'error': 'dataset_path parameter is required'}
    
    url = normalize_dataset_path(dataset_path)
    
    async with aiohttp.ClientSession() as session:
        data = await fetch_dataset(session, url)
    
    if 'error' in data:
        return data
    
    # Build structured result
    result = {
        'success': True,
        'url': data.get('url', url),
        'title': data.get('title', ''),
    }
    
    # Extract from JSON-LD
    json_ld = data.get('json_ld', {})
    if json_ld:
        result['name'] = json_ld.get('name', '')
        result['description'] = json_ld.get('description', '')
        result['license'] = json_ld.get('license', '')
        result['source_organization'] = json_ld.get('sourceOrganization', '')
    
    # Process resources
    resources = data.get('resources', [])
    if resources:
        result['resources'] = []
        for res in resources:
            resource = {
                'description': res.get('description', ''),
                'type': res.get('resource_type', ''),
                'arn': res.get('amazon_resource_name_arn', ''),
                'region': res.get('aws_region', ''),
            }
            result['resources'].append(resource)
        result['resource_count'] = len(resources)
    
    return result


async def list_datasets(params: dict[str, Any]) -> dict[str, Any]:
    """List datasets from the RSS feed"""
    limit = params.get('limit', 50)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                'https://registry.opendata.aws/rss.xml',
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    return {'error': f'HTTP {response.status} fetching RSS feed'}
                
                rss_content = await response.text()
        except aiohttp.ClientError as e:
            return {'error': str(e)}
    
    # Parse RSS feed
    datasets = []
    item_pattern = re.compile(r'<item>(.*?)</item>', re.DOTALL)
    
    for match in item_pattern.finditer(rss_content):
        item = match.group(1)
        
        title_match = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        link_match = re.search(r'<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', item, re.DOTALL)
        desc_match = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
        
        if title_match and link_match:
            title = title_match.group(1).strip()
            link = link_match.group(1).strip()
            description = desc_match.group(1).strip() if desc_match else ''
            
            # Extract dataset path from link
            dataset_path = link.replace('https://registry.opendata.aws', '').rstrip('/')
            
            datasets.append({
                'title': title,
                'path': dataset_path,
                'url': link,
                'description': description[:500] if description else '',
            })
            
            if len(datasets) >= limit:
                break
    
    return {
        'success': True,
        'count': len(datasets),
        'datasets': datasets,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the AWS Open Data Registry skill.
    
    Parameters:
        function: The function to call ('get_dataset' or 'list_datasets')
        dataset_path: Dataset path (e.g., 'nasa-nasa-ssh' or '/nasa-nasa-ssh/')
                     Required for 'get_dataset' function
        limit: Maximum number of datasets to return (default: 50)
               Used by 'list_datasets' function
    
    Returns:
        Structured dataset metadata including name, description, resources,
        ARNs, and AWS regions.
    """
    function = params.get('function', '')
    
    if function == 'get_dataset':
        return await get_dataset(params)
    elif function == 'list_datasets':
        return await list_datasets(params)
    else:
        return {
            'error': f'Unknown function: {function}. '
                    'Available functions: get_dataset, list_datasets'
        }