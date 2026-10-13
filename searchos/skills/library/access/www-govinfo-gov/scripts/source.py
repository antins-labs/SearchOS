"""
GovInfo Access Skill

Fetches budget tables and government documents from www.govinfo.gov.
Supports MODS metadata retrieval, XLSX spreadsheet downloads, and HTML page parsing.

Key endpoints:
- MODS metadata: https://www.govinfo.gov/metadata/pkg/{package_id}/mods.xml
- XLSX downloads: https://www.govinfo.gov/content/pkg/{package_id}/xls/{granule_id}.xlsx
- PDF downloads: https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf
- App details: https://www.govinfo.gov/app/details/{package_id}/{granule_id}
"""

import asyncio
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Optional
import aiohttp


# XML namespaces
MODS_NS = {'mods': 'http://www.loc.gov/mods/v3'}
XLSX_NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


async def _fetch_url(url: str, headers: dict = None, session: aiohttp.ClientSession = None) -> tuple[int, bytes]:
    """Fetch a URL and return (status_code, data)."""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; SearchOS/1.0)',
        'Accept': '*/*',
    }
    if headers:
        default_headers.update(headers)
    
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    
    try:
        async with session.get(url, headers=default_headers, allow_redirects=True) as resp:
            data = await resp.read()
            return resp.status, data
    finally:
        if own_session:
            await session.close()


def _parse_mods_metadata(xml_data: bytes, include_granules: bool = True) -> dict:
    """Parse MODS XML metadata into a structured dictionary."""
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        return {'error': f'Failed to parse MODS XML: {e}', 'raw_size': len(xml_data)}
    
    result = {
        'titles': [],
        'identifiers': [],
        'genres': [],
        'publishers': [],
        'dates': [],
        'abstracts': [],
        'granules': [],
        'subjects': [],
    }
    
    # Titles
    for title in root.findall('.//mods:titleInfo/mods:title', MODS_NS):
        if title.text:
            result['titles'].append(title.text)
    
    # Identifiers
    for ident in root.findall('.//mods:identifier', MODS_NS):
        id_type = ident.get('type', 'unknown')
        if ident.text:
            result['identifiers'].append({'type': id_type, 'value': ident.text})
    
    # Genres
    for genre in root.findall('.//mods:genre', MODS_NS):
        if genre.text:
            result['genres'].append(genre.text)
    
    # Publishers
    for pub in root.findall('.//mods:publisher', MODS_NS):
        if pub.text:
            result['publishers'].append(pub.text)
    
    # Dates
    for date in root.findall('.//mods:dateIssued', MODS_NS):
        if date.text:
            result['dates'].append(date.text)
    
    # Abstracts/Notes
    for abstract in root.findall('.//mods:abstract', MODS_NS):
        if abstract.text:
            result['abstracts'].append(abstract.text)
    
    # Subjects
    for subject in root.findall('.//mods:subject/mods:topic', MODS_NS):
        if subject.text:
            result['subjects'].append(subject.text)
    
    # Related items (granules/individual tables)
    # Only include items of type "constituent" which represent actual documents
    for item in root.findall('.//mods:relatedItem', MODS_NS):
        item_type = item.get('type', '')
        
        # Only process constituent items (actual documents/tables)
        if item_type != 'constituent':
            continue
        
        granule = {}
        
        # Title
        title_elem = item.find('.//mods:title', MODS_NS)
        if title_elem is not None and title_elem.text:
            granule['title'] = title_elem.text.strip()
        
        # Get granule identifier from URI
        for ident in item.findall('.//mods:identifier', MODS_NS):
            id_type = ident.get('type', '')
            if id_type == 'uri' and ident.text:
                uri = ident.text
                # Extract granule ID from URI like: 
                # https://www.govinfo.gov/app/details/BUDGET-2025-TAB/BUDGET-2025-TAB-2-1
                if '/' in uri:
                    granule['uri'] = uri
                    granule['granule_id'] = uri.split('/')[-1]
                    break
        
        # Get XLSX and PDF URLs if available
        for url_elem in item.findall('.//mods:url', MODS_NS):
            if url_elem.text:
                if '.xlsx' in url_elem.text:
                    granule['xlsx_url'] = url_elem.text
                elif '.pdf' in url_elem.text:
                    granule['pdf_url'] = url_elem.text
        
        # Only add if we have a title and granule_id
        if granule.get('title') and granule.get('granule_id'):
            result['granules'].append(granule)
    
    return result


def _parse_xlsx_data(xlsx_data: bytes, max_rows: int = None) -> dict:
    """Parse XLSX spreadsheet data into rows/columns."""
    try:
        with zipfile.ZipFile(io.BytesIO(xlsx_data), 'r') as zf:
            # Parse shared strings
            shared_strings = []
            try:
                ss_xml = zf.read('xl/sharedStrings.xml').decode('utf-8')
                ss_root = ET.fromstring(ss_xml)
                for si in ss_root.findall('.//s:si', XLSX_NS):
                    text_parts = []
                    for t in si.findall('.//s:t', XLSX_NS):
                        if t.text:
                            text_parts.append(t.text)
                    shared_strings.append(''.join(text_parts))
            except KeyError:
                pass  # No shared strings
            
            # Parse first worksheet
            sheet_files = [f for f in zf.namelist() if f.startswith('xl/worksheets/sheet')]
            if not sheet_files:
                return {'error': 'No worksheets found in XLSX'}
            
            sheet_xml = zf.read(sheet_files[0]).decode('utf-8')
            sheet_root = ET.fromstring(sheet_xml)
            
            rows = []
            for row_elem in sheet_root.findall('.//s:row', XLSX_NS):
                row_num = int(row_elem.get('r', '0'))
                cells = []
                
                for cell in row_elem.findall('s:c', XLSX_NS):
                    cell_type = cell.get('t')
                    value = cell.find('s:v', XLSX_NS)
                    
                    if value is not None and value.text:
                        v = value.text
                        if cell_type == 's':  # shared string reference
                            idx = int(v)
                            cells.append(shared_strings[idx] if idx < len(shared_strings) else v)
                        elif cell_type == 'b':  # boolean
                            cells.append(v == '1')
                        elif cell_type == 'n' or cell_type is None:  # number
                            try:
                                if '.' in v:
                                    cells.append(float(v))
                                else:
                                    cells.append(int(v))
                            except ValueError:
                                cells.append(v)
                        else:
                            cells.append(v)
                    else:
                        cells.append(None)
                
                rows.append({'row_number': row_num, 'cells': cells})
                
                if max_rows and len(rows) >= max_rows:
                    break
            
            return {
                'row_count': len(rows),
                'shared_strings_count': len(shared_strings),
                'rows': rows,
            }
    
    except zipfile.BadZipFile as e:
        return {'error': f'Invalid XLSX file (not a valid ZIP/XLSX format). This granule may not have an XLSX version.'}
    except ET.ParseError as e:
        return {'error': f'Failed to parse XLSX XML: {e}'}


async def get_package_metadata(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """Get MODS metadata for a govinfo package.
    
    Required params:
        - package_id: Package identifier (e.g., 'BUDGET-2025-TAB')
    
    Optional params:
        - include_granules: Include list of granules (default: true)
    """
    package_id = params.get('package_id')
    if not package_id:
        return {'error': 'Missing required parameter: package_id'}
    
    include_granules = params.get('include_granules', True)
    
    url = f'https://www.govinfo.gov/metadata/pkg/{package_id}/mods.xml'
    status, data = await _fetch_url(url, session=session)
    
    if status != 200:
        return {
            'error': f'Failed to fetch MODS metadata',
            'status_code': status,
            'url': url,
        }
    
    result = _parse_mods_metadata(data, include_granules=include_granules)
    result['package_id'] = package_id
    result['url'] = url
    result['status_code'] = status
    
    return result


async def get_granule_xlsx(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """Download and parse XLSX spreadsheet for a granule.
    
    Required params:
        - package_id: Package identifier (e.g., 'BUDGET-2025-TAB')
        - granule_id: Granule identifier (e.g., 'BUDGET-2025-TAB-2-1')
    
    Optional params:
        - max_rows: Maximum number of rows to return (default: 100)
        - raw_data: Return raw XLSX bytes instead of parsed data (default: false)
    """
    package_id = params.get('package_id')
    granule_id = params.get('granule_id')
    
    if not package_id:
        return {'error': 'Missing required parameter: package_id'}
    if not granule_id:
        return {'error': 'Missing required parameter: granule_id'}
    
    max_rows = params.get('max_rows', 100)
    raw_data = params.get('raw_data', False)
    
    url = f'https://www.govinfo.gov/content/pkg/{package_id}/xls/{granule_id}.xlsx'
    status, data = await _fetch_url(
        url, 
        headers={'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
        session=session
    )
    
    if status != 200:
        return {
            'error': f'Failed to fetch XLSX file (status {status}). This granule may not have an XLSX version. '
                     f'PDF may be available at: https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf',
            'status_code': status,
            'url': url,
            'pdf_url': f'https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf',
        }
    
    if raw_data:
        import base64
        return {
            'package_id': package_id,
            'granule_id': granule_id,
            'url': url,
            'content_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'size': len(data),
            'data_base64': base64.b64encode(data).decode('ascii'),
        }
    
    result = _parse_xlsx_data(data, max_rows=max_rows)
    result['package_id'] = package_id
    result['granule_id'] = granule_id
    result['url'] = url
    result['status_code'] = status
    result['size_bytes'] = len(data)
    
    return result


async def get_granule_pdf_url(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """Get the PDF download URL for a granule.
    
    Required params:
        - package_id: Package identifier
        - granule_id: Granule identifier
    
    Returns the direct PDF URL (does not download the file).
    """
    package_id = params.get('package_id')
    granule_id = params.get('granule_id')
    
    if not package_id:
        return {'error': 'Missing required parameter: package_id'}
    if not granule_id:
        return {'error': 'Missing required parameter: granule_id'}
    
    url = f'https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf'
    
    # Verify URL is accessible
    status, _ = await _fetch_url(url, headers={'Accept': 'application/pdf'}, session=session)
    
    return {
        'package_id': package_id,
        'granule_id': granule_id,
        'pdf_url': url,
        'accessible': status == 200,
        'status_code': status,
    }


async def get_premis_metadata(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """Get PREMIS preservation metadata for a package.
    
    Required params:
        - package_id: Package identifier
    """
    package_id = params.get('package_id')
    if not package_id:
        return {'error': 'Missing required parameter: package_id'}
    
    url = f'https://www.govinfo.gov/metadata/pkg/{package_id}/premis.xml'
    status, data = await _fetch_url(url, session=session)
    
    if status != 200:
        return {
            'error': f'Failed to fetch PREMIS metadata',
            'status_code': status,
            'url': url,
        }
    
    result = {
        'package_id': package_id,
        'url': url,
        'status_code': status,
        'size_bytes': len(data),
    }
    
    # Parse PREMIS XML
    try:
        root = ET.fromstring(data)
        result['premis'] = {}
        
        # Extract basic info
        for obj in root.findall('.//{info:lc/xmlns/premis-v2}object'):
            obj_id = obj.find('.//{info:lc/xmlns/premis-v2}objectIdentifierValue')
            if obj_id is not None and obj_id.text:
                result['premis']['object_id'] = obj_id.text
        
        for event in root.findall('.//{info:lc/xmlns/premis-v2}event'):
            event_type = event.find('.//{info:lc/xmlns/premis-v2}eventType')
            event_date = event.find('.//{info:lc/xmlns/premis-v2}eventDateTime')
            if event_type is not None and event_type.text:
                if 'events' not in result['premis']:
                    result['premis']['events'] = []
                result['premis']['events'].append({
                    'type': event_type.text,
                    'date': event_date.text if event_date is not None else None,
                })
    except ET.ParseError:
        result['parse_error'] = 'Failed to parse PREMIS XML'
    
    return result


async def list_package_contents(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """List all granules (tables/documents) in a package.
    
    Required params:
        - package_id: Package identifier
    
    Uses MODS metadata to extract the complete list of granules.
    """
    metadata = await get_package_metadata({'package_id': params.get('package_id')}, session=session)
    
    if 'error' in metadata:
        return metadata
    
    granules = metadata.get('granules', [])
    
    return {
        'package_id': metadata.get('package_id'),
        'title': metadata['titles'][0] if metadata.get('titles') else None,
        'granule_count': len(granules),
        'granules': granules,
    }


async def search_budget_tables(params: dict, session: aiohttp.ClientSession = None) -> dict:
    """Search for budget tables matching a pattern.
    
    Required params:
        - package_id: Package identifier (e.g., 'BUDGET-2025-TAB')
    
    Optional params:
        - query: Search query for table titles (case-insensitive substring match)
        - section: Filter by section number (e.g., '1', '2', '3')
        - has_xlsx: Only return granules that have XLSX files (default: true for tables)
        - max_results: Maximum number of results (default: 20)
    """
    package_id = params.get('package_id')
    if not package_id:
        return {'error': 'Missing required parameter: package_id'}
    
    query = params.get('query', '').lower()
    section = params.get('section')
    has_xlsx = params.get('has_xlsx', True)
    max_results = params.get('max_results', 20)
    
    metadata = await get_package_metadata({'package_id': package_id, 'include_granules': True}, session=session)
    
    if 'error' in metadata:
        return metadata
    
    granules = metadata.get('granules', [])
    results = []
    
    for granule in granules:
        title = granule.get('title', '').lower()
        granule_id = granule.get('granule_id', '')
        
        # Filter for XLSX availability (tables have XLSX, sections don't)
        if has_xlsx and not granule.get('xlsx_url'):
            # Also check if granule_id matches a table pattern (ends in -N-N, not just -N)
            # Table IDs are like BUDGET-2025-TAB-2-1, sections are BUDGET-2025-TAB-2
            parts = granule_id.split('-')
            if len(parts) < 5:  # Not a table pattern
                continue
        
        # Apply filters
        if query and query not in title:
            continue
        
        if section:
            # Check if granule ID has matching section number
            # BUDGET-2025-TAB-2-1 -> section is parts[-2] = 2
            parts = granule_id.split('-')
            if len(parts) >= 5:
                granule_section = parts[-2]
                if granule_section != section:
                    continue
        
        result = {
            'title': granule.get('title'),
            'granule_id': granule_id,
            'uri': granule.get('uri'),
            'xlsx_url': granule.get('xlsx_url') or f'https://www.govinfo.gov/content/pkg/{package_id}/xls/{granule_id}.xlsx',
            'pdf_url': granule.get('pdf_url') or f'https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf',
            'details_url': f'https://www.govinfo.gov/app/details/{package_id}/{granule_id}',
        }
        
        # Indicate if XLSX is verified from metadata
        result['has_xlsx'] = bool(granule.get('xlsx_url'))
        
        results.append(result)
        
        if len(results) >= max_results:
            break
    
    return {
        'package_id': package_id,
        'query': query if query else None,
        'section': section if section else None,
        'has_xlsx_filter': has_xlsx,
        'total_matching': len(results),
        'results': results,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the GovInfo access skill.
    
    Dispatches based on the 'function' parameter:
    
    - get_package_metadata: Get MODS metadata for a package
    - get_granule_xlsx: Download and parse XLSX spreadsheet
    - get_granule_pdf_url: Get PDF download URL
    - get_premis_metadata: Get PREMIS preservation metadata
    - list_package_contents: List all granules in a package
    - search_budget_tables: Search tables by title or section
    """
    function = params.get('function')
    
    if not function:
        return {'error': 'Missing required parameter: function'}
    
    # Optional session can be passed via context
    session = getattr(ctx, 'session', None) if ctx else None
    
    functions = {
        'get_package_metadata': get_package_metadata,
        'get_granule_xlsx': get_granule_xlsx,
        'get_granule_pdf_url': get_granule_pdf_url,
        'get_premis_metadata': get_premis_metadata,
        'list_package_contents': list_package_contents,
        'search_budget_tables': search_budget_tables,
    }
    
    if function not in functions:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': list(functions.keys()),
        }
    
    try:
        return await functions[function](params, session=session)
    except Exception as e:
        return {
            'error': f'Function execution failed: {str(e)}',
            'function': function,
            'params': {k: v for k, v in params.items() if k != 'function'},
        }