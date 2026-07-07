"""
SearchOS Access Skill for data.hereandthere.club
National Park Visitation Data Extractor

This skill extracts visitation statistics from National Park Service data hosted on
data.hereandthere.club, which provides historical and current visitation data for
all NPS units (national parks, monuments, memorials, etc.).
"""

import asyncio
import re
import json
from typing import Any, Optional
from urllib.parse import urljoin
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://data.hereandthere.club"

# Default headers to mimic a browser
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def parse_number(value: str) -> Optional[float]:
    """Parse a number string like '4.62M', '320.4K', or '1,234' into a float."""
    if not value:
        return None
    
    value = value.strip().replace(',', '').replace('%', '')
    
    multiplier = 1
    if value.endswith('M'):
        multiplier = 1_000_000
        value = value[:-1]
    elif value.endswith('K'):
        multiplier = 1_000
        value = value[:-1]
    
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def parse_percentage(value: str) -> Optional[float]:
    """Parse a percentage string like '-1.5%' or '+9.5%' into a float."""
    if not value:
        return None
    
    value = value.strip().replace('%', '').replace('+', '')
    try:
        return float(value)
    except ValueError:
        return None


def extract_park_slug_and_year(url: str) -> tuple[Optional[str], Optional[int]]:
    """Extract park slug and optional year from URL."""
    match = re.match(r'.*/national-park-visitation/([^/]+)(?:/(\d{4}))?', url)
    if match:
        slug = match.group(1)
        year = int(match.group(2)) if match.group(2) else None
        return slug, year
    return None, None


def extract_park_name_from_title(title: str) -> str:
    """Extract park name from page title like 'Zion NP Visitation Data & Statistics (2023)'"""
    if not title:
        return ""
    
    # Remove common suffixes
    title = re.sub(r'\s+Visitation Data & Statistics.*$', '', title, flags=re.I)
    title = re.sub(r'\s*\(\d{4}\)\s*$', '', title)
    
    # Replace abbreviations at word boundaries only
    # Order matters - replace longer matches first
    replacements = [
        (r'\bNMEM\b', 'National Memorial'),
        (r'\bNHS\b', 'National Historic Site'),
        (r'\bNHP\b', 'National Historical Park'),
        (r'\bNRA\b', 'National Recreation Area'),
        (r'\bNBR\b', 'National Biological Reserve'),
        (r'\bNMP\b', 'National Military Park'),
        (r'\bNP\b', 'National Park'),
        (r'\bNM\b', 'National Monument'),
        (r'\bNL\b', 'National Lakeshore'),
        (r'\bNR\b', 'National River'),
    ]
    
    for pattern, replacement in replacements:
        title = re.sub(pattern, replacement, title)
    
    return title.strip()


def parse_html(html: str, url: str) -> dict[str, Any]:
    """Parse HTML and extract visitation data."""
    soup = BeautifulSoup(html, 'html.parser')
    result = {
        'url': url,
        'success': False,
        'error': None,
        'data': {}
    }
    
    try:
        # Extract JSON-LD data first
        json_ld_data = []
        for ld in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(ld.string)
                json_ld_data.append(data)
            except:
                pass
        
        # Get page title for park name
        title = soup.find('title')
        if title:
            title_text = title.get_text()
            result['data']['title'] = title_text
            
            # Extract park name from title
            park_name = extract_park_name_from_title(title_text)
            if park_name:
                result['data']['park_name'] = park_name
            
            # Extract year from title
            year_match = re.search(r'\((\d{4})\)', title_text)
            if year_match:
                result['data']['year'] = int(year_match.group(1))
        
        # Get h1 for park name if title didn't work
        h1 = soup.find('h1')
        if h1:
            h1_text = h1.get_text()
            h1_text = re.sub(r'\s*\(\d{4}\)\s*$', '', h1_text)
            h1_text = re.sub(r'\s+Visitation Data & Statistics.*$', '', h1_text, flags=re.I)
            if h1_text and 'park_name' not in result['data']:
                result['data']['park_name'] = h1_text.strip()
        
        # Get meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            description = meta_desc.get('content', '')
            result['data']['description'] = description
            
            # Parse stats from description
            visits_match = re.search(r'([\d.]+[MK])\s+recreation\s+visits?', description, re.I)
            if visits_match:
                result['data']['recreation_visits_str'] = visits_match.group(1)
                result['data']['recreation_visits'] = parse_number(visits_match.group(1))
            
            overnight_match = re.search(r'([\d.]+[MK])\s+overnight\s+stays?', description, re.I)
            if overnight_match:
                result['data']['overnight_stays_str'] = overnight_match.group(1)
                result['data']['overnight_stays'] = parse_number(overnight_match.group(1))
            
            # Try to extract state from description
            state_match = re.search(r'data for .+ in ([A-Z]{2})[,.\\s]', description)
            if state_match:
                result['data']['state'] = state_match.group(1)
        
        # Extract FAQ data for structured stats
        faqs = []
        for ld in json_ld_data:
            if ld.get('@type') == 'FAQPage':
                for item in ld.get('mainEntity', []):
                    question = item.get('name', '')
                    answer = item.get('acceptedAnswer', {}).get('text', '')
                    faqs.append({'question': question, 'answer': answer})
                    
                    # Parse stats from FAQ answers
                    if 'recreation visits' in answer.lower() and 'recreation_visits' not in result['data']:
                        match = re.search(r'([\d.]+[MK])\s*recreation\s*visits?', answer, re.I)
                        if match:
                            result['data']['recreation_visits_str'] = match.group(1)
                            result['data']['recreation_visits'] = parse_number(match.group(1))
                    
                    if 'overnight stays' in answer.lower() and 'overnight_stays' not in result['data']:
                        match = re.search(r'([\d.]+[MK])\s*overnight\s*stays?', answer, re.I)
                        if match:
                            result['data']['overnight_stays_str'] = match.group(1)
                            result['data']['overnight_stays'] = parse_number(match.group(1))
                    
                    if 'recreation hours' in answer.lower() and 'recreation_hours' not in result['data']:
                        match = re.search(r'([\d.]+[MK])\s*recreation\s*hours?', answer, re.I)
                        if match:
                            result['data']['recreation_hours_str'] = match.group(1)
                            result['data']['recreation_hours'] = parse_number(match.group(1))
                    
                    # Parse rank from FAQ
                    rank_match = re.search(r'ranks?\s*#(\d+)\s*out of\s*(\d+)', answer, re.I)
                    if rank_match:
                        result['data']['rank'] = int(rank_match.group(1))
                        result['data']['total_in_category'] = int(rank_match.group(2))
                    
                    # Extract total campers from FAQ
                    campers_match = re.search(r'([\d.]+[MK])\s*total campers', answer, re.I)
                    if campers_match:
                        result['data']['total_campers_str'] = campers_match.group(1)
                        result['data']['total_campers'] = parse_number(campers_match.group(1))
        
        result['data']['faqs'] = faqs
        
        # Extract park designation from FAQ
        for faq in faqs:
            answer = faq.get('answer', '')
            desig_match = re.search(r'among the (\d+) (national parks|national monuments|national memorials)', answer, re.I)
            if desig_match:
                count = int(desig_match.group(1))
                desig_type = desig_match.group(2).title()
                result['data']['designation'] = desig_type
                result['data']['total_in_designation'] = count
                break
        
        # Parse main content from visible text
        body = soup.find('body')
        if body:
            text = body.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Extract key statistics from labeled sections
            stats = {}
            stat_labels = [
                'RECREATION VISITS', 'TOTAL VISITS', 'OVERNIGHT STAYS', 
                'TOTAL CAMPERS', 'AVG VISIT DURATION', 'PEAK MONTH',
                'RECREATION HOURS', 'NON-RECREATION VISITS', 'NON-RECREATION HOURS'
            ]
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                for label in stat_labels:
                    if label in line.upper():
                        if i + 1 < len(lines):
                            value_line = lines[i + 1]
                            
                            if 'PEAK MONTH' in label.upper():
                                if re.match(r'^[A-Z][a-z]+$', value_line):
                                    stats['peak_month'] = value_line
                                    break
                            elif re.match(r'^[\d.,]+[MKh]?$', value_line) or re.match(r'^\d+h$', value_line):
                                key = label.lower().replace(' ', '_')
                                stats[key] = {
                                    'value_str': value_line,
                                    'value': parse_number(value_line.replace('h', ''))
                                }
                                
                                if i + 2 < len(lines):
                                    pct_line = lines[i + 2]
                                    if '%' in pct_line and 'vs' in pct_line.lower():
                                        stats[key]['change_str'] = pct_line
                                        stats[key]['change'] = parse_percentage(pct_line)
                
                i += 1
            
            if stats:
                result['data']['statistics'] = stats
            
            # Extract camping breakdown
            camping_stats = {}
            for i, line in enumerate(lines):
                if line in ['Tent Campers', 'RV Campers', 'Backcountry Campers']:
                    if i + 2 < len(lines):
                        pct = lines[i + 1] if '%' in lines[i + 1] else None
                        val = lines[i + 2] if i + 2 < len(lines) and re.match(r'^[\d.,]+[MK]?$', lines[i + 2]) else None
                        if pct and val:
                            camping_stats[line.lower().replace(' ', '_')] = {
                                'percentage': parse_percentage(pct),
                                'value_str': val,
                                'value': parse_number(val)
                            }
            
            if camping_stats:
                result['data']['camping'] = camping_stats
            
            # Extract overnight stays breakdown
            overnight_stats = {}
            for i, line in enumerate(lines):
                if line in ['Tent Camping', 'RV Camping', 'Backcountry', 'Concessioner Lodging', 'Misc Overnight']:
                    if i + 2 < len(lines):
                        pct = lines[i + 1] if '%' in lines[i + 1] else None
                        val = lines[i + 2] if i + 2 < len(lines) and re.match(r'^[\d.,]+[MK]?$', lines[i + 2]) else None
                        if pct and val:
                            overnight_stats[line.lower().replace(' ', '_')] = {
                                'percentage': parse_percentage(pct),
                                'value_str': val,
                                'value': parse_number(val)
                            }
            
            if overnight_stats:
                result['data']['overnight_breakdown'] = overnight_stats
            
            # Extract visit types breakdown
            visit_types = {}
            for i, line in enumerate(lines):
                if line in ['Recreation Visits', 'Non-Recreation Visits']:
                    if i + 2 < len(lines):
                        pct = lines[i + 1] if '%' in lines[i + 1] else None
                        val = lines[i + 2] if i + 2 < len(lines) and re.match(r'^[\d.,]+[MK]?$', lines[i + 2]) else None
                        if pct and val:
                            visit_types[line.lower().replace(' ', '_')] = {
                                'percentage': parse_percentage(pct),
                                'value_str': val,
                                'value': parse_number(val)
                            }
            
            if visit_types:
                result['data']['visit_types'] = visit_types
            
            # Extract park info
            park_info = {}
            for i, line in enumerate(lines):
                if line == 'LOCATION' and i + 1 < len(lines):
                    park_info['state'] = lines[i + 1]
                elif line == 'REGION' and i + 1 < len(lines):
                    park_info['region'] = lines[i + 1]
                elif line == 'ESTABLISHED' and i + 1 < len(lines):
                    park_info['established'] = lines[i + 1]
                elif line == 'SIZE' and i + 1 < len(lines):
                    park_info['size'] = lines[i + 1]
            
            if park_info:
                result['data']['park_info'] = park_info
            
            # Extract seasonality data
            peak_match = re.search(r'peaking at ([\d,]+) visits in (\w+)', text)
            if peak_match:
                result['data']['peak_month_visits'] = parse_number(peak_match.group(1))
                if 'peak_month' not in result['data']:
                    result['data']['peak_month'] = peak_match.group(2)
            
            quiet_match = re.search(r'(\w+) was the quietest at ([\d,]+)', text)
            if quiet_match:
                result['data']['quietest_month'] = quiet_match.group(1)
                result['data']['quietest_month_visits'] = parse_number(quiet_match.group(2))
        
        # Extract slug from URL
        slug, year = extract_park_slug_and_year(url)
        if slug:
            result['data']['slug'] = slug
        
        if 'year' not in result['data'] and year:
            result['data']['year'] = year
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Fetch a page and return status code and content."""
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
            html = await response.text()
            return response.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the national park visitation data extraction.
    
    Parameters:
        function: str - One of:
            - "get_park_data": Get visitation data for a specific park/year
            - "list_parks": List parks by designation
            - "get_summary": Get summary statistics
        
        For "get_park_data":
            park: str - Park slug (e.g., "zion", "yellowstone", "pearl-harbor-nmem")
            year: int - Optional year (default: most recent available, typically 2025)
        
        For "list_parks":
            designation: str - Optional filter by designation 
                            (e.g., "national-parks", "national-monuments", "national-memorials")
        
        For "get_summary":
            (no additional parameters)
    
    Returns:
        dict with 'success', 'error', and 'data' fields
    """
    function = params.get("function", "get_park_data")
    
    async with aiohttp.ClientSession() as session:
        if function == "get_park_data":
            park = params.get("park", "").lower().strip()
            if not park:
                return {
                    "success": False,
                    "error": "Missing required parameter: park",
                    "data": None
                }
            
            year = params.get("year")
            
            if year:
                url = f"{BASE_URL}/national-park-visitation/{park}/{year}"
            else:
                url = f"{BASE_URL}/national-park-visitation/{park}"
            
            status, html = await fetch_page(session, url)
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status}: Failed to fetch {url}",
                    "data": None
                }
            
            result = parse_html(html, url)
            return result
        
        elif function == "list_parks":
            designation = params.get("designation", "")
            
            if designation:
                url = f"{BASE_URL}/national-park-visitation/designation/{designation}"
            else:
                url = f"{BASE_URL}/national-park-visitation"
            
            status, html = await fetch_page(session, url)
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status}: Failed to fetch {url}",
                    "data": None
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            parks = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/national-park-visitation/' in href:
                    parts = href.split('/national-park-visitation/')[-1].split('/')
                    if parts and parts[0] and parts[0] not in ['designation', 'compare', 'summary', '']:
                        slug = parts[0]
                        if not slug.isdigit() and slug != 'rankings':
                            name = link.get_text(strip=True)
                            if name and slug and len(name) > 1:
                                parks.append({
                                    'name': name,
                                    'slug': slug,
                                    'url': urljoin(BASE_URL, href)
                                })
            
            seen = set()
            unique_parks = []
            for park in parks:
                if park['slug'] not in seen:
                    seen.add(park['slug'])
                    unique_parks.append(park)
            
            return {
                "success": True,
                "error": None,
                "data": {
                    "url": url,
                    "designation": designation,
                    "parks": unique_parks,
                    "count": len(unique_parks)
                }
            }
        
        elif function == "get_summary":
            url = f"{BASE_URL}/national-park-visitation"
            
            status, html = await fetch_page(session, url)
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"HTTP {status}: Failed to fetch {url}",
                    "data": None
                }
            
            soup = BeautifulSoup(html, 'html.parser')
            summary = {'url': url}
            
            for ld in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(ld.string)
                    if data.get('@type') == 'Dataset':
                        summary['dataset'] = data
                except:
                    pass
            
            body = soup.find('body')
            if body:
                text = body.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                stats = {}
                for i, line in enumerate(lines):
                    if re.match(r'^[\d.]+[MK]?$', line) and i > 0:
                        label = lines[i-1] if i > 0 else None
                        if label and len(label) < 100 and not re.match(r'^[\d.]+[MK]?$', label):
                            stats[label] = {
                                'value_str': line,
                                'value': parse_number(line)
                            }
                
                summary['statistics'] = stats
            
            return {
                "success": True,
                "error": None,
                "data": summary
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. Valid functions: get_park_data, list_parks, get_summary",
                "data": None
            }


if __name__ == "__main__":
    import json
    
    async def test():
        result = await execute({"function": "get_park_data", "park": "zion", "year": 2023})
        print(json.dumps(result, indent=2, default=str))
    
    asyncio.run(test())