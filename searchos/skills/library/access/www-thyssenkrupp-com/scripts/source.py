"""
ThyssenKrupp History Access Skill

Fetches structured history timeline data from thyssenkrupp.com company history page.
The page embeds timeline data in a TRANSFER_STATE JavaScript object that contains
the complete history timeline with years, events, and images.
"""

import aiohttp
import json
import re
from typing import Any


async def _extract_transfer_state(html: str) -> dict:
    """Extract and parse the TRANSFER_STATE JSON from HTML."""
    start_marker = "window['TRANSFER_STATE'] = "
    start_idx = html.find(start_marker)
    
    if start_idx == -1:
        raise ValueError("TRANSFER_STATE not found in page HTML")
    
    start_idx += len(start_marker)
    
    # Parse JSON with proper string and brace handling
    brace_count = 0
    end_idx = start_idx
    in_string = False
    escape_next = False
    
    for i, char in enumerate(html[start_idx:], start_idx):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
    
    json_str = html[start_idx:end_idx]
    return json.loads(json_str)


async def _fetch_page_content(url: str) -> dict:
    """Fetch page and extract content from TRANSFER_STATE."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}: Failed to fetch page")
            
            html = await response.text()
    
    transfer_state = await _extract_transfer_state(html)
    
    # Find the content-path API key
    content_key = None
    for key in transfer_state:
        if '/_api/content-path/' in key and 'history' in key:
            content_key = key
            break
    
    if not content_key:
        raise ValueError("Content API data not found in TRANSFER_STATE")
    
    api_data = transfer_state[content_key]
    nested = json.loads(api_data['response'])
    content = nested['body']['body']
    
    return content


def _process_image_url(image_source: str, api_host: str = "https://www.thyssenkrupp.com/") -> str:
    """Process image URL to make it absolute."""
    if not image_source:
        return ""
    
    if image_source.startswith("dynimg.v1:"):
        # Dynamic image URL
        return image_source.replace("dynimg.v1:", "")
    elif image_source.startswith("../../"):
        # Relative URL
        return api_host + image_source[6:]  # Remove "../../"
    elif image_source.startswith("/"):
        return api_host.rstrip("/") + image_source
    elif not image_source.startswith("http"):
        return api_host + image_source
    
    return image_source


async def get_history_timeline(params: dict) -> dict:
    """
    Fetch the complete history timeline from thyssenkrupp.com.
    
    Returns a structured timeline with all historical events from 1811 to present.
    """
    url = "https://www.thyssenkrupp.com/en/company/history"
    
    try:
        content = await _fetch_page_content(url)
        
        # Find the history-timeline component
        bottom_wide = content.get('elements', {}).get('bottom-wide', [])
        timeline_data = None
        
        for item in bottom_wide:
            if item.get('className') == 'history-timeline':
                timeline_data = item.get('element', {})
                break
        
        if not timeline_data:
            return {
                "success": False,
                "error": "History timeline component not found on page",
                "data": None
            }
        
        # Process history points
        history_points = timeline_data.get('historyPointList', [])
        events = []
        
        for point in history_points:
            elem = point.get('element', {})
            
            event = {
                "date": elem.get('date', ''),
                "headline": elem.get('headline', ''),
                "is_divider": elem.get('divider', False),
                "image": _process_image_url(elem.get('image', {}).get('source', '') if isinstance(elem.get('image'), dict) else ''),
                "dom": elem.get('dom', '').strip() if elem.get('dom') else None,
            }
            
            # Add link if present
            link = elem.get('link', {})
            if link and isinstance(link, dict):
                link_elem = link.get('element', {})
                if link_elem.get('link'):
                    event['link'] = {
                        'url': link_elem.get('link', ''),
                        'text': link_elem.get('text', ''),
                    }
            
            events.append(event)
        
        # Process date list (era markers)
        date_list = timeline_data.get('dateList', [])
        eras = []
        current_era = None
        
        for item in date_list:
            if not item.get('isDivider', True):
                # This is an era marker
                if current_era:
                    eras.append(current_era)
                current_era = {
                    "period": item.get('year', ''),
                    "years": []
                }
            else:
                # This is a year within an era
                if current_era:
                    current_era['years'].append(item.get('year', ''))
        
        if current_era:
            eras.append(current_era)
        
        return {
            "success": True,
            "error": None,
            "data": {
                "page_title": content.get('pageTitle', '').strip() if content.get('pageTitle') else 'History',
                "total_events": len(events),
                "events": events,
                "eras": eras,
                "timeline_id": timeline_data.get('id'),
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


async def get_founding_families(params: dict) -> dict:
    """
    Fetch information about the founding families from the history page.
    
    Returns details about the Krupp and Thyssen founding family members.
    """
    url = "https://www.thyssenkrupp.com/en/company/history"
    
    try:
        content = await _fetch_page_content(url)
        
        # Find the image-teaser-slider component (founding families)
        bottom_wide = content.get('elements', {}).get('bottom-wide', [])
        families_data = None
        
        for item in bottom_wide:
            if item.get('className') == 'image-teaser-slider':
                families_data = item.get('element', {})
                break
        
        if not families_data:
            return {
                "success": False,
                "error": "Founding families slider not found on page",
                "data": None
            }
        
        # Process founding families
        teaser_list = families_data.get('teaserList', [])
        families = []
        
        for teaser in teaser_list:
            elem = teaser.get('element', {})
            link_elem = elem.get('link', {}).get('element', {})
            image_elem = elem.get('image', {})
            
            family_member = {
                "name": elem.get('subHeadlineHtml', '').replace('<p>', '').replace('</p>', '').strip(),
                "description": image_elem.get('text', '') if isinstance(image_elem, dict) else '',
                "link": link_elem.get('link', ''),
                "image": _process_image_url(image_elem.get('source', '') if isinstance(image_elem, dict) else ''),
            }
            
            families.append(family_member)
        
        return {
            "success": True,
            "error": None,
            "data": {
                "total_members": len(families),
                "founding_families": families,
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


async def get_page_content(params: dict) -> dict:
    """
    Fetch general content sections from the history page.
    
    Returns teaser sections, big image teasers, and other content areas.
    """
    url = "https://www.thyssenkrupp.com/en/company/history"
    
    try:
        content = await _fetch_page_content(url)
        
        sections = []
        bottom_wide = content.get('elements', {}).get('bottom-wide', [])
        
        for item in bottom_wide:
            class_name = item.get('className', '')
            elem = item.get('element', {})
            
            # Skip timeline (handled by get_history_timeline)
            if class_name == 'history-timeline':
                continue
            
            section = {
                "type": class_name,
                "id": elem.get('id'),
            }
            
            # Extract relevant data based on type
            if class_name == 'big-image-teaser':
                teaser_list = elem.get('teaserList', [])
                if teaser_list:
                    teaser = teaser_list[0].get('element', {}).get('teaserList', [])
                    if teaser:
                        teaser_elem = teaser[0].get('element', {})
                        section['headline'] = teaser_elem.get('headline', '').replace('<p>', '').replace('</p>', '').strip()
                        section['description'] = teaser_elem.get('copyText', '').replace('<p>', '').replace('</p>', '').strip()
                        link = teaser_elem.get('link', {}).get('element', {})
                        if link.get('link'):
                            section['link'] = {
                                'url': link.get('link', ''),
                                'text': link.get('text', ''),
                            }
                        image = teaser_elem.get('image', {})
                        if image:
                            section['image'] = {
                                'title': image.get('title', ''),
                                'url': _process_image_url(image.get('source', '')),
                            }
            
            elif class_name == 'standard-text':
                section['html'] = elem.get('bodyHtml', '')
            
            elif class_name == 'text-teaser-list':
                text_teasers = elem.get('textTeaserList', [])
                section['teasers'] = []
                for tt in text_teasers:
                    tt_elem = tt.get('element', {})
                    link = tt_elem.get('link', {}).get('element', {})
                    section['teasers'].append({
                        'headline': tt_elem.get('headlineHtml', '').replace('<p>', '').replace('</p>', '').strip(),
                        'text': tt_elem.get('textHtml', '').replace('<p>', '').replace('</p>', '').strip() if tt_elem.get('textHtml') else '',
                        'link': link.get('link', ''),
                    })
            
            elif class_name == 'contact-teaser':
                section['headline'] = elem.get('headline', '')
                section['contact'] = elem.get('contact', {})
            
            sections.append(section)
        
        return {
            "success": True,
            "error": None,
            "data": {
                "page_title": content.get('pageTitle', '').strip() if content.get('pageTitle') else 'History',
                "sections": sections,
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the thyssenkrupp history access skill.
    
    Dispatches based on the 'function' parameter:
    - get_history_timeline: Fetch the complete history timeline (1811-present)
    - get_founding_families: Fetch founding family members information
    - get_page_content: Fetch general page content sections
    """
    function = params.get('function', '')
    
    if function == 'get_history_timeline':
        return await get_history_timeline(params)
    elif function == 'get_founding_families':
        return await get_founding_families(params)
    elif function == 'get_page_content':
        return await get_page_content(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_history_timeline, get_founding_families, get_page_content",
            "data": None
        }