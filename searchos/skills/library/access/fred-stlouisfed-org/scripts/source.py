"""
FRED (Federal Reserve Economic Data) Access Skill

Provides access to time series data and metadata from the Federal Reserve Bank of St. Louis.
Supports:
- Retrieving time series data (observations) as CSV
- Retrieving comprehensive metadata for series
- Searching for series by keywords

API Endpoints:
- Data: https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID
- Metadata: https://fred.stlouisfed.org/graph/api/series/?id=SERIES_ID
- Series page: https://fred.stlouisfed.org/series/SERIES_ID
"""

import asyncio
import json
import re
from typing import Any, Optional
from datetime import datetime

import aiohttp


async def _fetch_url(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str, str]:
    """Fetch URL and return (status, content_type, content)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            content_type = resp.headers.get('content-type', '')
            content = await resp.text()
            return resp.status, content_type, content
    except asyncio.TimeoutError:
        return 0, '', f'Error: Request timed out after {timeout}s'
    except Exception as e:
        return 0, '', f'Error: {str(e)}'


async def _fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, dict]:
    """Fetch URL and return (status, json_data or error dict)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if 'json' in resp.headers.get('content-type', ''):
                data = await resp.json()
                return resp.status, data
            else:
                return resp.status, {'error': 'Response is not JSON', 'content_type': resp.headers.get('content-type')}
    except asyncio.TimeoutError:
        return 0, {'error': f'Request timed out after {timeout}s'}
    except json.JSONDecodeError as e:
        return 0, {'error': f'JSON decode error: {str(e)}'}
    except Exception as e:
        return 0, {'error': str(e)}


def _parse_csv_data(csv_content: str) -> dict:
    """Parse FRED CSV data into structured format."""
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        return {'error': 'No data in CSV', 'raw': csv_content}
    
    # Parse header
    header = lines[0].split(',')
    series_id = header[1] if len(header) > 1 else 'unknown'
    
    # Parse observations
    observations = []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) >= 2:
            date = parts[0].strip()
            value_str = parts[1].strip()
            # Handle missing values (represented as '.')
            if value_str and value_str != '.':
                try:
                    value = float(value_str)
                    observations.append({'date': date, 'value': value})
                except ValueError:
                    observations.append({'date': date, 'value': None, 'raw_value': value_str})
            else:
                observations.append({'date': date, 'value': None})
    
    return {
        'series_id': series_id,
        'observation_count': len(observations),
        'observations': observations,
        'date_range': {
            'start': observations[0]['date'] if observations else None,
            'end': observations[-1]['date'] if observations else None
        }
    }


async def get_series_data(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve time series data (observations) for a FRED series.
    
    Parameters:
        series_id: FRED series identifier (e.g., 'GFDEBTN', 'FYFR', 'GDP')
        start_date: Optional start date filter (YYYY-MM-DD format)
        end_date: Optional end date filter (YYYY-MM-DD format)
        transformation: Optional data transformation:
            - 'lin': Levels (default)
            - 'chg': Change
            - 'ch1': Change from Year Ago
            - 'pch': Percent Change
            - 'pc1': Percent Change from Year Ago
            - 'pca': Compounded Annual Rate of Change
            - 'cch': Continuously Compounded Rate of Change
            - 'cca': Continuously Compounded Annual Rate of Change
            - 'log': Natural Log
    
    Returns:
        Dict with series_id, observations, date_range, observation_count
    """
    series_id = (params.get('series_id') or '').strip().upper()
    if not series_id:
        return {'error': 'Missing required parameter: series_id', 'success': False}
    
    # Build URL
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    
    # Add transformation if specified
    transformation = (params.get('transformation') or '').lower()
    if transformation and transformation != 'lin':
        url += f"&transformation={transformation}"
    
    # Note: FRED CSV endpoint doesn't support date filtering directly via URL params
    # We'll filter the results after fetching
    
    status, content_type, content = await _fetch_url(session, url)
    
    if status != 200:
        return {
            'error': f'Failed to fetch data (status {status})',
            'series_id': series_id,
            'success': False
        }
    
    # Parse CSV
    result = _parse_csv_data(content)
    result['success'] = True
    result['source_url'] = url
    
    # Apply date filtering if specified
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    
    if start_date or end_date:
        filtered_obs = []
        for obs in result.get('observations', []):
            date = obs.get('date', '')
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            filtered_obs.append(obs)
        
        result['observations'] = filtered_obs
        result['observation_count'] = len(filtered_obs)
        if filtered_obs:
            result['date_range'] = {
                'start': filtered_obs[0]['date'],
                'end': filtered_obs[-1]['date']
            }
        result['date_filtered'] = True
    
    return result


async def get_series_metadata(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve comprehensive metadata for a FRED series.
    
    Parameters:
        series_id: FRED series identifier (e.g., 'GFDEBTN', 'FYFR', 'GDP')
    
    Returns:
        Dict with title, frequency, units, date_range, source, last_updated, etc.
    """
    series_id = (params.get('series_id') or '').strip().upper()
    if not series_id:
        return {'error': 'Missing required parameter: series_id', 'success': False}
    
    # Fetch metadata from Graph API
    url = f"https://fred.stlouisfed.org/graph/api/series/?id={series_id}&width=1140"
    status, data = await _fetch_json(session, url)
    
    if status != 200:
        return {
            'error': f'Failed to fetch metadata (status {status})',
            'series_id': series_id,
            'success': False
        }
    
    if 'error' in data:
        return {**data, 'series_id': series_id, 'success': False}
    
    if data.get('status') != 'true' or not data.get('chart_series'):
        return {
            'error': 'Series not found or invalid response',
            'series_id': series_id,
            'success': False
        }
    
    # Extract metadata from response
    chart_series = data['chart_series'][0] if data['chart_series'] else {}
    series_obj = chart_series.get('series_objects', {}).get('a', {})
    chart = data.get('chart', {})
    labels = chart.get('labels', {})
    
    result = {
        'success': True,
        'series_id': series_obj.get('series_id', series_id),
        'title': series_obj.get('title'),
        'subtitle': labels.get('subtitle'),
        'frequency': series_obj.get('frequency'),
        'frequency_short': series_obj.get('frequency_short'),
        'seasonal_adjustment': series_obj.get('season'),
        'seasonal_adjustment_short': series_obj.get('season_short'),
        'units': series_obj.get('units'),
        'units_short': series_obj.get('units_short'),
        'date_range': {
            'start': chart_series.get('min_date'),
            'end': chart_series.get('max_date')
        },
        'last_updated': series_obj.get('last_updated'),
        'notes': series_obj.get('notes'),
        'keywords': series_obj.get('keywords'),
        'available_transformations': list(series_obj.get('all_obs_transformations', {}).keys()),
        'transformation_descriptions': series_obj.get('all_obs_transformations', {}),
        'source_url': f"https://fred.stlouisfed.org/series/{series_id}",
        'api_url': url
    }
    
    # Also fetch the series page for additional metadata (tags, category, source)
    page_url = f"https://fred.stlouisfed.org/series/{series_id}"
    status, content_type, html = await _fetch_url(session, page_url)
    
    if status == 200:
        # Extract JSON-LD
        json_ld_match = re.search(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if json_ld_match:
            try:
                json_ld = json.loads(json_ld_match.group(1))
                result['description'] = json_ld.get('description')
                result['date_modified'] = json_ld.get('dateModified')
                result['license'] = json_ld.get('license')
            except json.JSONDecodeError:
                pass
        
        # Extract meta description
        meta_desc = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
        if meta_desc:
            result['meta_description'] = meta_desc.group(1)
        
        # Extract tags
        tags = re.findall(r'<meta[^>]*name="series-tag"[^>]*content="([^"]+)"', html)
        if tags:
            result['tags'] = tags
        
        # Extract category
        cat_match = re.search(r'href="/categories/(\d+)"[^>]*>([^<]+)</a>', html)
        if cat_match:
            result['category'] = {
                'id': cat_match.group(1),
                'name': cat_match.group(2).strip()
            }
    
    return result


async def search_series(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Search for FRED series by keyword.
    
    Parameters:
        query: Search query string
        limit: Maximum number of results to return (default 20, max 100)
        offset: Offset for pagination (default 0)
    
    Returns:
        Dict with search results including series_id, title, frequency, date_range, etc.
    """
    query = (params.get('query') or '').strip()
    if not query:
        return {'error': 'Missing required parameter: query', 'success': False}
    
    limit = min(int(params.get('limit') or 20), 100)
    offset = int(params.get('offset') or 0)
    
    # Fetch search results page
    search_url = f"https://fred.stlouisfed.org/search?st={query}"
    
    status, content_type, html = await _fetch_url(session, search_url)
    
    if status != 200:
        return {
            'error': f'Search failed (status {status})',
            'query': query,
            'success': False
        }
    
    # Parse search results from HTML
    # FRED search results are in <tr> elements with class "fred-serie-list-item" or in a table
    results = []
    
    # Pattern to match series list items - looking for series ID links
    # <a href="/series/GFDEBTN" class="series-title ...">...</a>
    series_pattern = re.compile(
        r'<a[^>]*href="/series/([A-Z0-9]+)"[^>]*class="[^"]*series-title[^"]*"[^>]*>([^<]+)</a>',
        re.IGNORECASE
    )
    
    for match in series_pattern.finditer(html):
        series_id = match.group(1).upper()
        title = match.group(2).strip()
        
        # Try to extract more info from the surrounding context
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 500)
        context = html[start:end]
        
        # Extract date range if available
        date_pattern = re.search(r'(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', context)
        date_start = date_pattern.group(1) if date_pattern else None
        date_end = date_pattern.group(2) if date_pattern else None
        
        # Extract frequency
        freq_match = re.search(r'(Daily|Weekly|Monthly|Quarterly|Annual|Semiannual)', context, re.IGNORECASE)
        frequency = freq_match.group(1) if freq_match else None
        
        results.append({
            'series_id': series_id,
            'title': title,
            'frequency': frequency,
            'date_range': {
                'start': date_start,
                'end': date_end
            } if date_start and date_end else None,
            'url': f"https://fred.stlouisfed.org/series/{series_id}"
        })
        
        if len(results) >= limit:
            break
    
    # Deduplicate by series_id
    seen = set()
    unique_results = []
    for r in results:
        if r['series_id'] not in seen:
            seen.add(r['series_id'])
            unique_results.append(r)
    
    # Apply offset
    unique_results = unique_results[offset:offset + limit]
    
    return {
        'success': True,
        'query': query,
        'result_count': len(unique_results),
        'results': unique_results,
        'search_url': search_url
    }


async def get_series_full(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve both metadata and data for a FRED series in a single call.
    
    Parameters:
        series_id: FRED series identifier
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        transformation: Optional transformation (see get_series_data)
        include_observations: Whether to include full observations (default True)
    
    Returns:
        Combined dict with metadata and data
    """
    series_id = (params.get('series_id') or '').strip().upper()
    if not series_id:
        return {'error': 'Missing required parameter: series_id', 'success': False}
    
    # Fetch metadata and data in parallel
    metadata_task = get_series_metadata({'series_id': series_id}, session)
    data_task = get_series_data({
        'series_id': series_id,
        'start_date': params.get('start_date'),
        'end_date': params.get('end_date'),
        'transformation': params.get('transformation')
    }, session)
    
    metadata, data = await asyncio.gather(metadata_task, data_task)
    
    result = {
        'success': metadata.get('success', False) and data.get('success', False),
        'series_id': series_id,
        'metadata': metadata,
        'data': {
            'observation_count': data.get('observation_count'),
            'date_range': data.get('date_range'),
        }
    }
    
    include_observations = params.get('include_observations', True)
    if include_observations:
        result['data']['observations'] = data.get('observations', [])
    else:
        # Just include summary stats
        observations = data.get('observations', [])
        if observations:
            values = [o['value'] for o in observations if o.get('value') is not None]
            if values:
                result['data']['summary'] = {
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'latest': values[-1] if values else None,
                    'latest_date': observations[-1]['date'] if observations else None
                }
    
    # Add any errors
    if metadata.get('error'):
        result['metadata_error'] = metadata['error']
    if data.get('error'):
        result['data_error'] = data['error']
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute FRED data access operations.
    
    Supported functions:
        - get_series_data: Retrieve time series observations
        - get_series_metadata: Retrieve series metadata
        - get_series_full: Retrieve both metadata and data
        - search_series: Search for series by keyword
    
    Parameters:
        function: One of 'get_series_data', 'get_series_metadata', 'get_series_full', 'search_series'
        series_id: FRED series ID (required for data/metadata functions)
        query: Search query (required for search_series)
        start_date: Optional start date filter
        end_date: Optional end date filter
        transformation: Optional data transformation
        limit: Max results for search (default 20)
        include_observations: Include full observations in get_series_full (default True)
    
    Returns:
        Dict with success status and requested data or error message.
    """
    function = params.get('function') or 'get_series_full'
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_series_data':
            return await get_series_data(params, session)
        elif function == 'get_series_metadata':
            return await get_series_metadata(params, session)
        elif function == 'get_series_full':
            return await get_series_full(params, session)
        elif function == 'search_series':
            return await search_series(params, session)
        else:
            return {
                'error': f'Unknown function: {function}. '
                         f'Supported: get_series_data, get_series_metadata, get_series_full, search_series',
                'success': False
            }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        print("Testing FRED Access Skill")
        print("=" * 60)
        
        # Test 1: Get series data
        print("\n1. Testing get_series_data (GFDEBTN):")
        result = await execute({'function': 'get_series_data', 'series_id': 'GFDEBTN'})
        print(f"   Success: {result.get('success')}")
        print(f"   Observation count: {result.get('observation_count')}")
        print(f"   Date range: {result.get('date_range')}")
        if result.get('observations'):
            print(f"   First 3 observations: {result['observations'][:3]}")
            print(f"   Last 3 observations: {result['observations'][-3:]}")
        
        # Test 2: Get series metadata
        print("\n2. Testing get_series_metadata (GFDEBTN):")
        result = await execute({'function': 'get_series_metadata', 'series_id': 'GFDEBTN'})
        print(f"   Success: {result.get('success')}")
        print(f"   Title: {result.get('title')}")
        print(f"   Frequency: {result.get('frequency')}")
        print(f"   Units: {result.get('units')}")
        print(f"   Date range: {result.get('date_range')}")
        print(f"   Tags: {result.get('tags', [])[:5]}")
        
        # Test 3: Get series full
        print("\n3. Testing get_series_full (FYFR):")
        result = await execute({
            'function': 'get_series_full',
            'series_id': 'FYFR',
            'include_observations': False
        })
        print(f"   Success: {result.get('success')}")
        print(f"   Metadata title: {result.get('metadata', {}).get('title')}")
        print(f"   Data observation count: {result.get('data', {}).get('observation_count')}")
        if result.get('data', {}).get('summary'):
            print(f"   Summary: {result['data']['summary']}")
        
        # Test 4: Search series
        print("\n4. Testing search_series:")
        result = await execute({'function': 'search_series', 'query': 'federal debt', 'limit': 5})
        print(f"   Success: {result.get('success')}")
        print(f"   Result count: {result.get('result_count')}")
        for r in result.get('results', [])[:3]:
            print(f"   - {r.get('series_id')}: {r.get('title')}")
        
        # Test 5: Get with date filtering
        print("\n5. Testing get_series_data with date filtering:")
        result = await execute({
            'function': 'get_series_data',
            'series_id': 'GFDEBTN',
            'start_date': '2020-01-01',
            'end_date': '2023-12-31'
        })
        print(f"   Success: {result.get('success')}")
        print(f"   Observation count: {result.get('observation_count')}")
        print(f"   Date range: {result.get('date_range')}")
        
        print("\n" + "=" * 60)
        print("All tests completed!")
    
    asyncio.run(test())