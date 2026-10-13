"""
SearchOS Access Skill for Natural England Defra ArcGIS Open Data

Provides access to the Areas of Outstanding Natural Beauty (AONB) England dataset
via the ArcGIS REST API.

Dataset: Areas of Outstanding Natural Beauty (England)
Source: Natural England / Defra
ArcGIS Service: services.arcgis.com/JJzESW51TqeY9uat
"""

import aiohttp
import asyncio
from typing import Any, Optional
import json

# ArcGIS Feature Service endpoint
BASE_URL = "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Areas_of_Outstanding_Natural_Beauty_England/FeatureServer"
LAYER_URL = f"{BASE_URL}/0"
QUERY_URL = f"{LAYER_URL}/query"

# Field definitions for reference
FIELDS = {
    'OBJECTID': 'int - Unique identifier',
    'CODE': 'str - 2-digit code for the AONB',
    'NAME': 'str - Name of the AONB',
    'DESIG_DATE': 'str - Designation date (e.g., "Sep-63")',
    'HOTLINK': 'str - URL to official AONB website',
    'STAT_AREA': 'float - Statistical area in square kilometers',
    'Shape__Area': 'float - Geometry area in map units',
    'Shape__Length': 'float - Geometry perimeter in map units',
    'GlobalID': 'str - Global unique identifier'
}


def _escape_sql_string(value: str) -> str:
    """Escape a string for use in SQL WHERE clause (single quotes)."""
    return value.replace("'", "''")


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a request to the Natural England AONB dataset.
    
    Parameters:
        params: dict containing:
            - function: str - One of 'list_aonbs', 'get_aonb', 'search', 'get_metadata'
            
            For 'list_aonbs':
                - include_geometry: bool (optional) - Include polygon geometries (default: false)
                - limit: int (optional) - Max records to return (default: all 34)
                - offset: int (optional) - Offset for pagination (default: 0)
                
            For 'get_aonb':
                - name: str (optional) - Name of AONB to retrieve
                - code: str (optional) - 2-digit code of AONB to retrieve
                - include_geometry: bool (optional) - Include polygon geometry (default: true)
                
            For 'search':
                - query: str (optional) - Search term for AONB name (case-insensitive substring match)
                - min_area: float (optional) - Minimum statistical area in km²
                - max_area: float (optional) - Maximum statistical area in km²
                - include_geometry: bool (optional) - Include polygon geometries (default: false)
                
            For 'get_metadata':
                - No additional parameters required
                
        ctx: Optional context (not used)
        
    Returns:
        dict containing:
            - success: bool
            - data: The requested data (structure varies by function)
            - error: str (if success is False)
    """
    func = params.get('function')
    
    if not func:
        return {
            'success': False,
            'error': "Missing required parameter 'function'. Must be one of: list_aonbs, get_aonb, search, get_metadata"
        }
    
    async with aiohttp.ClientSession() as session:
        if func == 'list_aonbs':
            return await _list_aonbs(session, params)
        elif func == 'get_aonb':
            return await _get_aonb(session, params)
        elif func == 'search':
            return await _search_aonbs(session, params)
        elif func == 'get_metadata':
            return await _get_metadata(session)
        else:
            return {
                'success': False,
                'error': f"Unknown function: {func}. Must be one of: list_aonbs, get_aonb, search, get_metadata"
            }


async def _query_features(
    session: aiohttp.ClientSession,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = False,
    result_offset: int = 0,
    result_record_count: Optional[int] = None,
    order_by: Optional[str] = None
) -> dict[str, Any]:
    """
    Execute a query against the ArcGIS Feature Service.
    
    Args:
        session: aiohttp ClientSession
        where: SQL where clause
        out_fields: Comma-separated list of field names or "*"
        return_geometry: Whether to include geometry
        result_offset: Offset for pagination
        result_record_count: Maximum records to return
        order_by: Field(s) to order by
        
    Returns:
        dict with features and metadata
    """
    post_data = {
        'f': 'json',
        'where': where,
        'outFields': out_fields,
        'returnGeometry': 'true' if return_geometry else 'false'
    }
    
    if result_record_count is not None:
        post_data['resultOffset'] = str(result_offset)
        post_data['resultRecordCount'] = str(result_record_count)
    
    if order_by:
        post_data['orderByFields'] = order_by
    
    try:
        async with session.post(QUERY_URL, data=post_data) as resp:
            if resp.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP error: {resp.status}',
                    'features': []
                }
            
            data = await resp.json()
            
            if 'error' in data:
                return {
                    'success': False,
                    'error': data['error'].get('message', 'Unknown ArcGIS error'),
                    'features': []
                }
            
            features = data.get('features', [])
            exceeded_limit = data.get('exceededTransferLimit', False)
            
            # Transform features to cleaner format
            records = []
            for f in features:
                record = {
                    'attributes': f.get('attributes', {})
                }
                if return_geometry and 'geometry' in f:
                    record['geometry'] = f['geometry']
                records.append(record)
            
            return {
                'success': True,
                'features': records,
                'exceeded_transfer_limit': exceeded_limit,
                'geometry_type': data.get('geometryType'),
                'spatial_reference': data.get('spatialReference'),
                'fields': data.get('fields', [])
            }
            
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}',
            'features': []
        }
    except json.JSONDecodeError as e:
        return {
            'success': False,
            'error': f'JSON decode error: {str(e)}',
            'features': []
        }


async def _get_count(session: aiohttp.ClientSession, where: str = "1=1") -> int:
    """Get the count of features matching the where clause."""
    params = {
        'f': 'json',
        'where': where,
        'returnCountOnly': 'true',
        'returnGeometry': 'false'
    }
    
    try:
        async with session.get(QUERY_URL, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('count', 0)
    except:
        pass
    return 0


async def _list_aonbs(session: aiohttp.ClientSession, params: dict[str, Any]) -> dict[str, Any]:
    """
    List all AONBs in the dataset.
    """
    include_geometry = params.get('include_geometry', False)
    limit = params.get('limit')
    offset = params.get('offset', 0)
    
    if isinstance(include_geometry, str):
        include_geometry = include_geometry.lower() in ('true', '1', 'yes')
    
    result = await _query_features(
        session,
        where="1=1",
        out_fields="*",
        return_geometry=include_geometry,
        result_offset=offset,
        result_record_count=limit,
        order_by="NAME"
    )
    
    if not result['success']:
        return result
    
    # Get total count
    total_count = await _get_count(session)
    
    # Transform to cleaner format
    aonbs = []
    for f in result['features']:
        attrs = f['attributes']
        aonb = {
            'object_id': attrs.get('OBJECTID'),
            'code': attrs.get('CODE'),
            'name': attrs.get('NAME'),
            'designation_date': attrs.get('DESIG_DATE'),
            'website_url': attrs.get('HOTLINK'),
            'area_sqkm': attrs.get('STAT_AREA'),
            'shape_area': attrs.get('Shape__Area'),
            'shape_length': attrs.get('Shape__Length'),
            'global_id': attrs.get('GlobalID')
        }
        if include_geometry and 'geometry' in f:
            aonb['geometry'] = f['geometry']
        aonbs.append(aonb)
    
    return {
        'success': True,
        'data': {
            'total_count': total_count,
            'returned_count': len(aonbs),
            'offset': offset,
            'limit': limit,
            'aonbs': aonbs
        }
    }


async def _get_aonb(session: aiohttp.ClientSession, params: dict[str, Any]) -> dict[str, Any]:
    """
    Get a specific AONB by name or code.
    """
    name = params.get('name')
    code = params.get('code')
    include_geometry = params.get('include_geometry', True)
    
    if isinstance(include_geometry, str):
        include_geometry = include_geometry.lower() in ('true', '1', 'yes')
    
    if not name and not code:
        return {
            'success': False,
            'error': "Either 'name' or 'code' parameter is required"
        }
    
    # Build where clause
    where_clauses = []
    if name:
        # Case-insensitive name match
        escaped_name = _escape_sql_string(name.upper())
        where_clauses.append(f"UPPER(NAME) = '{escaped_name}'")
    if code:
        escaped_code = _escape_sql_string(code)
        where_clauses.append(f"CODE = '{escaped_code}'")
    
    where_clause = " AND ".join(where_clauses)
    
    result = await _query_features(
        session,
        where=where_clause,
        out_fields="*",
        return_geometry=include_geometry
    )
    
    if not result['success']:
        return result
    
    features = result['features']
    
    if not features:
        return {
            'success': False,
            'error': f"No AONB found matching the criteria"
        }
    
    # Return first match
    f = features[0]
    attrs = f['attributes']
    
    aonb = {
        'object_id': attrs.get('OBJECTID'),
        'code': attrs.get('CODE'),
        'name': attrs.get('NAME'),
        'designation_date': attrs.get('DESIG_DATE'),
        'website_url': attrs.get('HOTLINK'),
        'area_sqkm': attrs.get('STAT_AREA'),
        'shape_area': attrs.get('Shape__Area'),
        'shape_length': attrs.get('Shape__Length'),
        'global_id': attrs.get('GlobalID'),
        'geometry_type': result.get('geometry_type'),
        'spatial_reference': result.get('spatial_reference')
    }
    
    if include_geometry and 'geometry' in f:
        aonb['geometry'] = f['geometry']
    
    return {
        'success': True,
        'data': aonb
    }


async def _search_aonbs(session: aiohttp.ClientSession, params: dict[str, Any]) -> dict[str, Any]:
    """
    Search AONBs by various criteria.
    """
    query = params.get('query')
    min_area = params.get('min_area')
    max_area = params.get('max_area')
    include_geometry = params.get('include_geometry', False)
    
    if isinstance(include_geometry, str):
        include_geometry = include_geometry.lower() in ('true', '1', 'yes')
    
    # Build where clause
    where_clauses = ["1=1"]
    
    if query:
        # Case-insensitive substring search on NAME
        escaped_query = _escape_sql_string(query.upper())
        where_clauses.append(f"UPPER(NAME) LIKE '%{escaped_query}%'")
    
    if min_area is not None:
        where_clauses.append(f"STAT_AREA >= {float(min_area)}")
    
    if max_area is not None:
        where_clauses.append(f"STAT_AREA <= {float(max_area)}")
    
    where_clause = " AND ".join(where_clauses)
    
    result = await _query_features(
        session,
        where=where_clause,
        out_fields="*",
        return_geometry=include_geometry,
        order_by="STAT_AREA DESC"
    )
    
    if not result['success']:
        return result
    
    # Get matching count
    matching_count = await _get_count(session, where_clause)
    
    # Transform results
    aonbs = []
    for f in result['features']:
        attrs = f['attributes']
        aonb = {
            'object_id': attrs.get('OBJECTID'),
            'code': attrs.get('CODE'),
            'name': attrs.get('NAME'),
            'designation_date': attrs.get('DESIG_DATE'),
            'website_url': attrs.get('HOTLINK'),
            'area_sqkm': attrs.get('STAT_AREA'),
            'shape_area': attrs.get('Shape__Area'),
            'shape_length': attrs.get('Shape__Length'),
            'global_id': attrs.get('GlobalID')
        }
        if include_geometry and 'geometry' in f:
            aonb['geometry'] = f['geometry']
        aonbs.append(aonb)
    
    return {
        'success': True,
        'data': {
            'total_matching': matching_count,
            'returned_count': len(aonbs),
            'search_criteria': {
                'query': query,
                'min_area': min_area,
                'max_area': max_area
            },
            'aonbs': aonbs
        }
    }


async def _get_metadata(session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Get metadata about the dataset and layer.
    """
    try:
        # Get service metadata
        async with session.get(f"{BASE_URL}?f=json") as resp:
            service_data = await resp.json() if resp.status == 200 else {}
        
        # Get layer metadata
        async with session.get(f"{LAYER_URL}?f=json") as resp:
            layer_data = await resp.json() if resp.status == 200 else {}
        
        # Get feature count
        count = await _get_count(session)
        
        # Extract relevant metadata
        metadata = {
            'service': {
                'name': 'Areas of Outstanding Natural Beauty England',
                'description': service_data.get('serviceDescription', ''),
                'current_version': service_data.get('currentVersion'),
                'max_record_count': service_data.get('maxRecordCount'),
                'supported_query_formats': service_data.get('supportedQueryFormats', ''),
                'has_static_data': service_data.get('hasStaticData', False)
            },
            'layer': {
                'id': layer_data.get('id', 0),
                'name': layer_data.get('name', ''),
                'type': layer_data.get('type', ''),
                'geometry_type': layer_data.get('geometryType', ''),
                'display_field': layer_data.get('displayField', ''),
                'extent': layer_data.get('extent', {}),
                'spatial_reference': layer_data.get('extent', {}).get('spatialReference', {}),
                'copyright_text': layer_data.get('copyrightText', ''),
                'last_edit_date': layer_data.get('editingInfo', {}).get('lastEditDate')
            },
            'fields': layer_data.get('fields', []),
            'feature_count': count,
            'capabilities': layer_data.get('capabilities', ''),
            'source_url': 'https://naturalengland-defra.opendata.arcgis.com/datasets/Defra::areas-of-outstanding-natural-beauty-england'
        }
        
        return {
            'success': True,
            'data': metadata
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve metadata: {str(e)}'
        }