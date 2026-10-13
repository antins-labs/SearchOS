"""
Hiroshima Peace Media - Peace Museums of the World
Access skill for www.hiroshimapeacemedia.jp/mediacenter_d/w_museum/

This skill provides access to the structured directory of peace museums worldwide,
organized by region (Japan, Asia, Africa, Europe, Americas, Oceania).
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup, NavigableString
from typing import Any
from urllib.parse import urljoin

BASE_URL = "https://www.hiroshimapeacemedia.jp/mediacenter_d/w_museum/"


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_museum_list(html: str) -> dict:
    """Parse the museum list page and return structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    regions = []
    current_region = None
    current_museums = []
    
    list_div = soup.find('div', class_='list')
    if not list_div:
        return {'regions': [], 'total_museums': 0}
    
    for child in list_div.children:
        if not hasattr(child, 'name') or not child.name:
            continue
            
        if child.name == 'h2':
            # Save previous region
            if current_region:
                regions.append({
                    'region': current_region,
                    'museums': current_museums
                })
            current_region = child.get_text(strip=True)
            current_museums = []
            
        elif child.name == 'ul':
            # Parse museums in this region
            for li in child.find_all('li', recursive=False):
                # Check if it's a country group (has nested ul)
                nested_ul = li.find('ul')
                if nested_ul:
                    # Extract country name (text before the nested ul)
                    country_text = li.get_text().split('\n')[0].strip()
                    country_name = country_text.rstrip(':').strip()
                    
                    # Get museums under this country
                    for museum_li in nested_ul.find_all('li'):
                        link = museum_li.find('a')
                        if link:
                            href = link.get('href', '')
                            current_museums.append({
                                'name': link.get_text(strip=True),
                                'url': urljoin(BASE_URL, href),
                                'slug': href.replace('_en.html', '').replace('.html', ''),
                                'country': country_name
                            })
                else:
                    # Direct museum link (Japan region doesn't have country groups)
                    link = li.find('a')
                    if link:
                        href = link.get('href', '')
                        current_museums.append({
                            'name': link.get_text(strip=True),
                            'url': urljoin(BASE_URL, href),
                            'slug': href.replace('_en.html', '').replace('.html', ''),
                            'country': None  # Japan museums don't have country field
                        })
    
    # Save last region
    if current_region:
        regions.append({
            'region': current_region,
            'museums': current_museums
        })
    
    total_museums = sum(len(r['museums']) for r in regions)
    
    return {
        'regions': regions,
        'total_museums': total_museums
    }


def parse_museum_detail(html: str) -> dict:
    """Parse a museum detail page and return structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'title': None,
        'region': None,
        'date': None,
        'author': None,
        'description': None,
        'address': None,
        'phone': None,
        'fax': None,
        'homepage': None,
        'hours': None,
        'days_closed': None,
        'admission': None,
        'photos': [],
        'related_museums': []
    }
    
    # Get title from h2
    h2 = soup.find('h2')
    if h2:
        result['title'] = h2.get_text(strip=True)
    
    # Get region from h1
    h1 = soup.find('h1')
    if h1:
        result['region'] = h1.get_text(strip=True)
    
    # Get main content
    ctMMain = soup.find('div', id='ctMMain')
    if not ctMMain:
        return result
    
    # Get date (in paragraph after h2)
    ctMHead = soup.find('div', id='ctMHead')
    if ctMHead:
        date_p = ctMHead.find('p')
        if date_p:
            result['date'] = date_p.get_text(strip=True)
    
    # Get left content div
    ctMLeft = ctMMain.find('div', id='ctMLeft')
    if ctMLeft:
        # Get the main paragraph with description
        main_p = ctMLeft.find('p')
        if main_p:
            # Extract author from first line
            text = main_p.get_text(separator='\n', strip=True)
            lines = text.split('\n')
            if lines and 'by ' in lines[0].lower():
                result['author'] = lines[0].strip()
                # Rest is description (until we hit structured info)
                desc_lines = []
                for line in lines[1:]:
                    line = line.strip()
                    if line.startswith('Address:') or line.startswith('Tel:') or line.startswith('Homepage:'):
                        break
                    if line:
                        desc_lines.append(line)
                result['description'] = ' '.join(desc_lines)
            else:
                # No author line, all is description
                desc_lines = []
                for line in lines:
                    line = line.strip()
                    if line.startswith('Address:') or line.startswith('Tel:') or line.startswith('Homepage:'):
                        break
                    if line:
                        desc_lines.append(line)
                result['description'] = ' '.join(desc_lines)
        
        # Extract structured info from strong tags
        # The format is: <strong>Label:</strong> value<br/>
        for strong in main_p.find_all('strong'):
            label = strong.get_text(strip=True).rstrip(':').strip()
            
            # The value is a NavigableString immediately after the strong tag
            # or an <a> tag for links
            value_parts = []
            next_node = strong.next_sibling
            while next_node:
                if isinstance(next_node, NavigableString):
                    text = str(next_node).strip()
                    if text:
                        value_parts.append(text)
                elif hasattr(next_node, 'name'):
                    if next_node.name == 'br':
                        break
                    if next_node.name == 'strong':
                        break
                    if next_node.name == 'a':
                        value_parts.append(next_node.get_text(strip=True))
                next_node = next_node.next_sibling
            
            value = ' '.join(value_parts).strip()
            
            label_lower = label.lower()
            if 'address' in label_lower:
                result['address'] = value
            elif label_lower in ('tel', 'phone'):
                result['phone'] = value
            elif label_lower == 'fax':
                result['fax'] = value
            elif 'homepage' in label_lower or 'url' in label_lower or 'website' in label_lower:
                result['homepage'] = value
            elif 'open' in label_lower or 'hours' in label_lower:
                result['hours'] = value
            elif 'closed' in label_lower or 'close' in label_lower:
                result['days_closed'] = value
            elif 'admission' in label_lower or 'fee' in label_lower:
                result['admission'] = value
    
    # Get photos from table
    photo_table = ctMMain.find('table', id='photogh')
    if photo_table:
        for img in photo_table.find_all('img'):
            src = img.get('src', '')
            if src:
                # Get caption from following paragraph
                caption = ''
                parent_td = img.find_parent('td')
                if parent_td:
                    caption_p = parent_td.find('p')
                    if caption_p:
                        caption = caption_p.get_text(strip=True)
                
                # Get original image link
                original_url = None
                parent_a = img.find_parent('a')
                if parent_a:
                    original_url = parent_a.get('href', '')
                
                result['photos'].append({
                    'thumbnail': urljoin(BASE_URL, src),
                    'original': urljoin(BASE_URL, original_url) if original_url else None,
                    'caption': caption
                })
    
    # Get related museums from sidebar
    border_div = soup.find('div', class_='border')
    if border_div:
        for link in border_div.find_all('a', href=True):
            href = link.get('href', '')
            if '_en.html' in href and link.get_text(strip=True):
                # Check if this is a museum link (not navigation)
                if not any(x in href for x in ['index_en', 'list_en']):
                    result['related_museums'].append({
                        'name': link.get_text(strip=True),
                        'url': urljoin(BASE_URL, href)
                    })
    
    return result


async def list_museums(params: dict) -> dict:
    """List all peace museums organized by region."""
    url = urljoin(BASE_URL, "list_en.html")
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(session, url)
            data = parse_museum_list(html)
            
            # Apply filters if provided
            region_filter = params.get('region', '').lower()
            country_filter = params.get('country', '').lower()
            
            if region_filter or country_filter:
                filtered_regions = []
                for region_data in data['regions']:
                    # Check region filter
                    if region_filter and region_filter not in region_data['region'].lower():
                        continue
                    
                    # Check country filter
                    if country_filter:
                        filtered_museums = [
                            m for m in region_data['museums']
                            if m.get('country') and country_filter in m['country'].lower()
                        ]
                        if filtered_museums:
                            filtered_regions.append({
                                'region': region_data['region'],
                                'museums': filtered_museums
                            })
                    else:
                        filtered_regions.append(region_data)
                
                data['regions'] = filtered_regions
                data['total_museums'] = sum(len(r['museums']) for r in filtered_regions)
            
            return {
                'success': True,
                'data': data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None
            }


async def get_museum(params: dict) -> dict:
    """Get details for a specific museum."""
    slug = params.get('slug', '')
    url = params.get('url', '')
    
    if not slug and not url:
        return {
            'success': False,
            'error': 'Either slug or url parameter is required',
            'data': None
        }
    
    if not url:
        # Construct URL from slug
        if not slug.endswith('_en'):
            slug = slug + '_en'
        url = urljoin(BASE_URL, f"{slug}.html")
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(session, url)
            data = parse_museum_detail(html)
            data['url'] = url
            return {
                'success': True,
                'data': data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None
            }


async def search_museums(params: dict) -> dict:
    """Search museums by name."""
    query = params.get('query', '').lower()
    if not query:
        return {
            'success': False,
            'error': 'Query parameter is required',
            'data': None
        }
    
    url = urljoin(BASE_URL, "list_en.html")
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(session, url)
            data = parse_museum_list(html)
            
            # Search through all museums
            results = []
            for region_data in data['regions']:
                for museum in region_data['museums']:
                    # Search in name and country
                    name = museum.get('name', '').lower()
                    country = museum.get('country', '') or ''
                    country = country.lower()
                    
                    if query in name or query in country:
                        results.append({
                            **museum,
                            'region': region_data['region']
                        })
            
            return {
                'success': True,
                'data': {
                    'query': params.get('query'),
                    'total_results': len(results),
                    'results': results
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None
            }


async def get_regions(params: dict) -> dict:
    """Get list of all regions with museum counts."""
    url = urljoin(BASE_URL, "list_en.html")
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_html(session, url)
            data = parse_museum_list(html)
            
            regions = []
            for region_data in data['regions']:
                regions.append({
                    'name': region_data['region'],
                    'museum_count': len(region_data['museums'])
                })
            
            return {
                'success': True,
                'data': {
                    'regions': regions,
                    'total_museums': data['total_museums']
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None
            }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Dispatches based on the 'function' parameter.
    """
    function = params.get('function', '')
    
    if function == 'list_museums':
        return await list_museums(params)
    elif function == 'get_museum':
        return await get_museum(params)
    elif function == 'search_museums':
        return await search_museums(params)
    elif function == 'get_regions':
        return await get_regions(params)
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Available functions: list_museums, get_museum, search_museums, get_regions',
            'data': None
        }