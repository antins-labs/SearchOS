"""
GDACS (Global Disaster Alert and Coordination System) Access Skill

Retrieves disaster alert information from GDACS including:
- Individual event reports (earthquakes, floods, tropical cyclones, etc.)
- Current alerts feed (RSS)
- Event-specific data (CAP, GeoJSON, shakemap)

Data sources:
- RSS feed: https://www.gdacs.org/xml/rss.xml
- CAP XML: https://www.gdacs.org/contentdata/resources/{type}/{id}/cap_{id}.xml
- GeoJSON: https://www.gdacs.org/contentdata/resources/{type}/{id}/geojson_{id}_{episode}.geojson
- Event RSS: https://www.gdacs.org/contentdata/resources/{type}/{id}/rss_{id}_{episode}.xml
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Any
from datetime import datetime
import json


async def fetch_url(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch URL and return (status, content)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/xml, application/json, text/html, */*',
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            return resp.status, await resp.text()
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 0, str(e)


def parse_cap_xml(xml_text: str) -> dict:
    """Parse CAP (Common Alerting Protocol) XML"""
    try:
        root = ET.fromstring(xml_text)
        ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        
        result = {
            'identifier': None,
            'sender': None,
            'sent': None,
            'status': None,
            'msgType': None,
            'scope': None,
            'incidents': None,
            'info': {}
        }
        
        # Alert-level elements
        for elem in ['identifier', 'sender', 'sent', 'status', 'msgType', 'scope', 'incidents']:
            el = root.find(f'cap:{elem}', ns)
            if el is not None and el.text:
                result[elem] = el.text
        
        # Info elements
        info = root.find('cap:info', ns)
        if info is not None:
            result['info'] = {
                'category': None,
                'event': None,
                'urgency': None,
                'severity': None,
                'certainty': None,
                'senderName': None,
                'headline': None,
                'description': None,
                'web': None,
                'parameters': {},
                'areas': []
            }
            
            for elem in ['category', 'event', 'urgency', 'severity', 'certainty', 'senderName', 'headline', 'description', 'web']:
                el = info.find(f'cap:{elem}', ns)
                if el is not None and el.text:
                    result['info'][elem] = el.text
            
            # Parameters
            for param in info.findall('cap:parameter', ns):
                value_name = param.find('cap:valueName', ns)
                value = param.find('cap:value', ns)
                if value_name is not None and value_name.text:
                    result['info']['parameters'][value_name.text] = value.text if value is not None else None
            
            # Areas
            for area in info.findall('cap:area', ns):
                area_data = {}
                area_desc = area.find('cap:areaDesc', ns)
                if area_desc is not None:
                    area_data['areaDesc'] = area_desc.text
                
                geocodes = {}
                for geocode in area.findall('cap:geocode', ns):
                    value_name = geocode.find('cap:valueName', ns)
                    value = geocode.find('cap:value', ns)
                    if value_name is not None and value_name.text:
                        geocodes[value_name.text] = value.text if value is not None else None
                if geocodes:
                    area_data['geocodes'] = geocodes
                
                polygon = area.find('cap:polygon', ns)
                if polygon is not None and polygon.text:
                    area_data['polygon'] = polygon.text
                
                circle = area.find('cap:circle', ns)
                if circle is not None and circle.text:
                    area_data['circle'] = circle.text
                
                if area_data:
                    result['info']['areas'].append(area_data)
        
        return result
    except ET.ParseError as e:
        return {'error': f'XML parse error: {str(e)}'}


def parse_rss_feed(xml_text: str) -> list[dict]:
    """Parse GDACS RSS feed"""
    try:
        root = ET.fromstring(xml_text)
        items = []
        
        for item in root.findall('.//item'):
            event = {}
            
            # Standard RSS elements
            for child in item:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                text = child.text.strip() if child.text and child.text.strip() else None
                
                if text:
                    event[tag] = text
                
                # Handle attributes
                if child.attrib:
                    if tag not in event:
                        event[tag] = {}
                    if isinstance(event[tag], dict):
                        event[tag].update(child.attrib)
                    elif text:
                        event[tag] = {'text': text, **child.attrib}
            
            items.append(event)
        
        return items
    except ET.ParseError as e:
        return [{'error': f'XML parse error: {str(e)}'}]


async def get_event_report(session: aiohttp.ClientSession, event_type: str, event_id: str) -> dict:
    """Get comprehensive event report from multiple sources"""
    result = {
        'event_type': event_type,
        'event_id': event_id,
        'sources': {},
        'data': {}
    }
    
    # Build URLs for different data sources
    # First, try to get the event RSS to find episode ID
    event_rss_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/rss_{event_id}.xml'
    status, rss_text = await fetch_url(session, event_rss_url)
    
    episode_id = None
    if status == 200 and rss_text:
        result['sources']['event_rss'] = {'url': event_rss_url, 'status': status}
        items = parse_rss_feed(rss_text)
        if items and not items[0].get('error'):
            result['data']['rss_items'] = items
            # Try to extract episode ID from first item
            if items and 'episodeid' in items[0]:
                episode_id = items[0].get('episodeid')
    
    # Try specific episode RSS if we found an episode ID
    if not episode_id:
        # Try to find episode ID from directory listing or CAP
        cap_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/cap_{event_id}.xml'
        status, cap_text = await fetch_url(session, cap_url)
        if status == 200 and cap_text:
            cap_data = parse_cap_xml(cap_text)
            if not cap_data.get('error'):
                result['sources']['cap'] = {'url': cap_url, 'status': status}
                result['data']['cap'] = cap_data
                
                # Extract episode ID from identifier
                identifier = cap_data.get('identifier', '')
                if identifier:
                    parts = identifier.split('_')
                    if len(parts) >= 3:
                        episode_id = parts[-1]
    
    # If we have episode ID, get more data
    if episode_id:
        result['episode_id'] = episode_id
        
        # GeoJSON
        geojson_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/geojson_{event_id}_{episode_id}.geojson'
        status, geojson_text = await fetch_url(session, geojson_url)
        if status == 200 and geojson_text:
            result['sources']['geojson'] = {'url': geojson_url, 'status': status}
            try:
                result['data']['geojson'] = json.loads(geojson_text)
            except:
                result['data']['geojson'] = {'raw': geojson_text[:500]}
        
        # Episode-specific RSS
        episode_rss_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/rss_{event_id}_{episode_id}.xml'
        status, rss_text = await fetch_url(session, episode_rss_url)
        if status == 200 and rss_text:
            result['sources']['episode_rss'] = {'url': episode_rss_url, 'status': status}
            items = parse_rss_feed(rss_text)
            if items and not items[0].get('error'):
                result['data']['episode_rss_items'] = items
        
        # Aftershock data (for earthquakes)
        if event_type == 'EQ':
            aftershock_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/aftershock.json'
            status, aftershock_text = await fetch_url(session, aftershock_url)
            if status == 200 and aftershock_text:
                result['sources']['aftershock'] = {'url': aftershock_url, 'status': status}
                try:
                    result['data']['aftershocks'] = json.loads(aftershock_text)
                except:
                    pass
    
    # If we still don't have CAP data, try to get it now
    if 'cap' not in result['data']:
        cap_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/cap_{event_id}.xml'
        status, cap_text = await fetch_url(session, cap_url)
        if status == 200 and cap_text:
            cap_data = parse_cap_xml(cap_text)
            if not cap_data.get('error'):
                result['sources']['cap'] = {'url': cap_url, 'status': status}
                result['data']['cap'] = cap_data
    
    return result


async def get_current_alerts(session: aiohttp.ClientSession, event_type: str = None, limit: int = 50) -> dict:
    """Get current alerts from RSS feed"""
    rss_url = 'https://www.gdacs.org/xml/rss.xml'
    status, rss_text = await fetch_url(session, rss_url)
    
    result = {
        'source': rss_url,
        'status': status,
        'alerts': []
    }
    
    if status != 200 or not rss_text:
        result['error'] = f'Failed to fetch RSS feed (status: {status})'
        return result
    
    items = parse_rss_feed(rss_text)
    
    # Filter by event type if specified
    if event_type:
        items = [item for item in items if item.get('eventtype') == event_type.upper()]
    
    # Limit results
    items = items[:limit]
    
    result['alerts'] = items
    result['total'] = len(items)
    
    return result


async def search_events(session: aiohttp.ClientSession, query: str = None, event_type: str = None, 
                        alert_level: str = None, limit: int = 20) -> dict:
    """Search events in current RSS feed"""
    rss_url = 'https://www.gdacs.org/xml/rss.xml'
    status, rss_text = await fetch_url(session, rss_url)
    
    result = {
        'source': rss_url,
        'status': status,
        'events': [],
        'filters': {
            'query': query,
            'event_type': event_type,
            'alert_level': alert_level
        }
    }
    
    if status != 200 or not rss_text:
        result['error'] = f'Failed to fetch RSS feed (status: {status})'
        return result
    
    items = parse_rss_feed(rss_text)
    
    # Apply filters
    filtered = []
    for item in items:
        match = True
        
        # Filter by event type
        if event_type:
            if item.get('eventtype', '').upper() != event_type.upper():
                match = False
        
        # Filter by alert level
        if alert_level and match:
            if item.get('alertlevel', '').lower() != alert_level.lower():
                match = False
        
        # Filter by query (search in title, description, country)
        if query and match:
            query_lower = query.lower()
            searchable = ' '.join([
                item.get('title', ''),
                item.get('description', ''),
                item.get('country', ''),
                item.get('eventname', '')
            ]).lower()
            if query_lower not in searchable:
                match = False
        
        if match:
            filtered.append(item)
    
    # Limit results
    result['events'] = filtered[:limit]
    result['total'] = len(filtered)
    result['total_available'] = len(items)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Main entry point for GDACS skill"""
    function = params.get('function', '')
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_event_report':
            event_type = params.get('event_type', 'EQ')
            event_id = params.get('event_id')
            
            if not event_id:
                return {'error': 'event_id is required'}
            
            return await get_event_report(session, event_type, event_id)
        
        elif function == 'get_current_alerts':
            event_type = params.get('event_type')
            limit = params.get('limit', 50)
            
            return await get_current_alerts(session, event_type, limit)
        
        elif function == 'search_events':
            query = params.get('query')
            event_type = params.get('event_type')
            alert_level = params.get('alert_level')
            limit = params.get('limit', 20)
            
            return await search_events(session, query, event_type, alert_level, limit)
        
        elif function == 'get_cap_alert':
            event_type = params.get('event_type', 'EQ')
            event_id = params.get('event_id')
            
            if not event_id:
                return {'error': 'event_id is required'}
            
            cap_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/cap_{event_id}.xml'
            status, cap_text = await fetch_url(session, cap_url)
            
            if status != 200 or not cap_text:
                return {'error': f'Failed to fetch CAP alert (status: {status})', 'url': cap_url}
            
            cap_data = parse_cap_xml(cap_text)
            return {
                'event_type': event_type,
                'event_id': event_id,
                'source': cap_url,
                'status': status,
                'cap': cap_data
            }
        
        elif function == 'get_geojson':
            event_type = params.get('event_type', 'EQ')
            event_id = params.get('event_id')
            episode_id = params.get('episode_id')
            
            if not event_id:
                return {'error': 'event_id is required'}
            if not episode_id:
                return {'error': 'episode_id is required (use get_event_report to find it)'}
            
            geojson_url = f'https://www.gdacs.org/contentdata/resources/{event_type}/{event_id}/geojson_{event_id}_{episode_id}.geojson'
            status, geojson_text = await fetch_url(session, geojson_url)
            
            if status != 200 or not geojson_text:
                return {'error': f'Failed to fetch GeoJSON (status: {status})', 'url': geojson_url}
            
            try:
                geojson_data = json.loads(geojson_text)
                return {
                    'event_type': event_type,
                    'event_id': event_id,
                    'episode_id': episode_id,
                    'source': geojson_url,
                    'status': status,
                    'geojson': geojson_data
                }
            except json.JSONDecodeError as e:
                return {'error': f'Failed to parse GeoJSON: {str(e)}', 'url': geojson_url}
        
        else:
            return {
                'error': f'Unknown function: {function}',
                'available_functions': [
                    'get_event_report - Get comprehensive report for a specific event',
                    'get_current_alerts - Get current alerts from RSS feed',
                    'search_events - Search events by query, type, or alert level',
                    'get_cap_alert - Get CAP (Common Alerting Protocol) XML for an event',
                    'get_geojson - Get GeoJSON data for an event'
                ]
            }