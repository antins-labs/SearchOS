"""
Nobel Prize Bibliography & Bio-bibliography Access Skill

Extracts structured bibliographical and biographical data from Nobel Prize website.
Supports two page types:
1. Individual laureate bibliography pages
2. Prize-year bio-bibliography pages (biography + bibliography)
"""

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


async def fetch_page(url: str) -> tuple[int, str | None]:
    """Fetch page content from Nobel Prize website."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            return response.status_code, response.text
        except Exception as e:
            return 0, str(e)


def parse_bibliography_entry(entry_text: str) -> dict[str, Any] | None:
    """Parse a single bibliography entry into structured format.
    
    Typical formats:
    - "Title. – Place : Publisher, Year"
    - "Title : subtitle. – Place : Publisher, Year. – (Series; vol)"
    - "Title / translated by X. – Place : Publisher, Year"
    """
    entry = entry_text.strip()
    if not entry or entry.isspace():
        return None
    
    result: dict[str, Any] = {"raw": entry}
    
    # Try to extract series info like "(Kristin Lavransdatter; 1)"
    series_match = re.search(r'\(([^)]+)\)', entry)
    if series_match:
        result['series'] = series_match.group(1)
    
    # Check for translation info
    trans_match = re.search(r'/\s*translated by\s+([^\.–]+)', entry, re.IGNORECASE)
    if trans_match:
        result['translator'] = trans_match.group(1).strip()
    
    # Check for original title (Translation of: ...)
    orig_match = re.search(r'Translation of:\s*([^\.–]+)', entry, re.IGNORECASE)
    if orig_match:
        result['original_title'] = orig_match.group(1).strip()
    
    # Also check for "Originaltitel:" and "Traduction de:" (German/French)
    orig_match2 = re.search(r'(?:Originaltitel|Traduction de):\s*([^\.–]+)', entry, re.IGNORECASE)
    if orig_match2:
        result['original_title'] = orig_match2.group(1).strip()
    
    # Split by ". –" which typically separates title from publication info
    parts = re.split(r'\.\s*[–—-]\s*', entry)
    
    if len(parts) >= 1:
        # First part is usually the title
        title_part = parts[0].strip()
        # Remove HTML tags if any
        title_part = re.sub(r'<[^>]+>', '', title_part)
        # Remove translator info from title
        if '/ translated' in title_part.lower():
            title_part = re.sub(r'\s*/\s*translated.*$', '', title_part, flags=re.IGNORECASE)
        result['title'] = title_part.strip()
    
    if len(parts) >= 2:
        # Second part is publication info: "Place : Publisher, Year"
        pub_info = parts[1].strip()
        
        # Extract year (4-digit number)
        year_match = re.search(r'\b(18|19|20)\d{2}\b', pub_info)
        if year_match:
            result['year'] = year_match.group(0)
        
        # Split by " : " to get place and publisher
        if ' : ' in pub_info:
            place_pub = pub_info.split(' : ', 1)
            result['place'] = place_pub[0].strip()
            if len(place_pub) > 1:
                pub_year = place_pub[1]
                # Remove year from publisher
                publisher = re.sub(r',\s*(18|19|20)\d{2}.*$', '', pub_year).strip()
                # Remove trailing series info
                publisher = re.sub(r'\.\s*[–—-].*$', '', publisher).strip()
                if publisher:
                    result['publisher'] = publisher
    
    return result


def extract_table_bibliography(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract bibliography from table format (individual laureate pages)."""
    result: dict[str, Any] = {
        "sections": [],
        "total_entries": 0,
    }
    
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        current_section = None
        section_entries = []
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                text = cell.get_text(strip=True)
                if not text:
                    continue
                
                # Check if this is a section header (bold text, no publication info)
                is_bold = cell.find('b') or cell.find('strong')
                has_year = re.search(r'\b(18|19|20)\d{2}\b', text)
                has_publisher_marker = ' : ' in text or '. –' in text or '.—' in text
                
                if is_bold and not has_year and not has_publisher_marker:
                    # Save previous section
                    if current_section and section_entries:
                        result['sections'].append({
                            'name': current_section,
                            'entries': section_entries
                        })
                        result['total_entries'] += len(section_entries)
                    
                    current_section = text
                    section_entries = []
                elif has_year or has_publisher_marker:
                    # This is a bibliography entry
                    parsed = parse_bibliography_entry(text)
                    if parsed:
                        section_entries.append(parsed)
        
        # Save last section
        if current_section and section_entries:
            result['sections'].append({
                'name': current_section,
                'entries': section_entries
            })
            result['total_entries'] += len(section_entries)
    
    return result


def is_bibliography_section(text: str, tag: str) -> bool:
    """Check if a heading indicates a bibliography section."""
    # Only h3, h4, h5, h6 can be bibliography sections
    if tag not in ['h3', 'h4', 'h5', 'h6']:
        return False
    
    text_lower = text.lower().strip()
    
    # Skip the main "Biobibliography" heading
    if 'biobibliography' in text_lower or 'bio-bibliography' in text_lower:
        return False
    
    # Skip PDF download sections
    if 'pdf' in text_lower or text_lower == 'english':
        return False
    
    # Keywords that indicate bibliography sections
    bib_keywords = [
        'bibliography',
        'in english', 'in french', 'in german', 'in swedish', 
        'in polish', 'in spanish', 'in italian',
        'translations', 'critical studies',
        'interviews', 'film', 'television', 'tv',
        'works in', 'writings', 'selected works',
        'publications', 'books', 'further reading'
    ]
    
    for kw in bib_keywords:
        if kw in text_lower:
            return True
    
    return False


def extract_bio_bibliography_text(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract biography and bibliography from paragraph format (bio-bibliography pages)."""
    result: dict[str, Any] = {
        "biography": [],
        "bibliography": {},
        'total_entries': 0
    }
    
    entry_content = soup.find(class_='entry-content')
    if not entry_content:
        return result
    
    in_bibliography = False  # Track if we've entered bibliography sections
    current_section = "biography"
    current_heading = None
    section_entries = []
    
    # Process all content elements
    for element in entry_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'table']):
        tag = element.name
        text = element.get_text(strip=True)
        
        # Skip navigation elements and empty text
        if not text or 'Navigate to:' in text:
            continue
        if element.find('select'):  # Skip select dropdowns
            continue
        
        # Skip PDF download links and similar
        if tag in ['h5', 'h4'] and ('pdf' in text.lower() or text.lower().strip() == 'english'):
            continue
        
        # Handle headings
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            if is_bibliography_section(text, tag):
                # Save previous section entries
                if section_entries:
                    if current_section in result['bibliography']:
                        result['bibliography'][current_section]['entries'].extend(section_entries)
                        result['total_entries'] += len(section_entries)
                    else:
                        result['bibliography'][current_section] = {
                            'name': current_heading or current_section,
                            'entries': section_entries
                        }
                        result['total_entries'] += len(section_entries)
                    section_entries = []
                
                in_bibliography = True
                current_section = text.lower().replace(' ', '_')[:50]
                current_heading = text
            else:
                # Could be other heading
                current_heading = text
        
        # Handle tables (some bio-bibliography pages have tables too)
        elif tag == 'table':
            table_data = extract_table_bibliography(BeautifulSoup(str(element), 'html.parser'))
            for section in table_data.get('sections', []):
                section_name = section['name'].lower().replace(' ', '_')[:50]
                if section_name in result['bibliography']:
                    result['bibliography'][section_name]['entries'].extend(section['entries'])
                else:
                    result['bibliography'][section_name] = section
                result['total_entries'] += len(section['entries'])
            in_bibliography = True
        
        # Handle paragraphs
        elif tag == 'p':
            text_lower = text.lower()
            
            # Skip footer/citation paragraphs
            if 'to cite this section' in text_lower or 'mla style:' in text_lower:
                continue
            if 'the swedish academy' in text_lower and len(text) < 50:
                continue
            
            # Detect bibliography entries: must have BOTH year AND publisher marker
            has_year = bool(re.search(r'\b(18|19|20)\d{2}\b', text))
            has_publisher_marker = ' : ' in text  # Place : Publisher format
            
            if has_year and has_publisher_marker:
                # This is a bibliography entry
                parsed = parse_bibliography_entry(text)
                if parsed:
                    section_entries.append(parsed)
                    in_bibliography = True
            elif not in_bibliography and len(text) > 100:
                # This is biographical text (only before we hit bibliography sections)
                result['biography'].append(text)
    
    # Save final section
    if section_entries:
        if current_section in result['bibliography']:
            result['bibliography'][current_section]['entries'].extend(section_entries)
            result['total_entries'] += len(section_entries)
        else:
            result['bibliography'][current_section] = {
                'name': current_heading or current_section,
                'entries': section_entries
            }
            result['total_entries'] += len(section_entries)
    
    return result


def extract_metadata(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract metadata from the page."""
    metadata: dict[str, Any] = {}
    
    # Get the main heading from section header
    section_header = soup.find(class_='section-header')
    if section_header:
        h1 = section_header.find('h1')
        if h1:
            metadata['laureate_name'] = h1.get_text(strip=True)
        h2 = section_header.find('h2')
        if h2:
            metadata['page_type'] = h2.get_text(strip=True)
    else:
        # Fallback to first h1
        h1 = soup.find('h1')
        if h1:
            metadata['title'] = h1.get_text(strip=True)
    
    h2 = soup.find('h2')
    if h2 and 'subtitle' not in metadata:
        metadata['subtitle'] = h2.get_text(strip=True)
    
    # Get page URL from canonical link
    canonical = soup.find('link', rel='canonical')
    if canonical and canonical.get('href'):
        metadata['url'] = canonical['href']
        
        # Extract prize info from URL
        url = canonical['href']
        parts = url.split('/prizes/')
        if len(parts) > 1:
            prize_parts = parts[1].strip('/').split('/')
            if len(prize_parts) >= 2:
                metadata['prize_category'] = prize_parts[0]
                try:
                    metadata['prize_year'] = int(prize_parts[1])
                except ValueError:
                    pass
            if len(prize_parts) >= 3 and prize_parts[2] not in ['bio-bibliography', 'summary']:
                metadata['laureate_slug'] = prize_parts[2]
    
    # Get total table summary if available
    table = soup.find('table')
    if table and table.get('summary'):
        metadata['table_summary'] = table['summary']
    
    return metadata


def extract_related_links(soup: BeautifulSoup, current_url: str) -> list[dict[str, str]]:
    """Extract related navigation links (facts, biography, speech, etc.)."""
    links = []
    seen = set()
    
    nav_select = soup.find('select', class_='aside-navigation')
    if nav_select:
        options = nav_select.find_all('option')
        for opt in options:
            value = opt.get('value', '')
            text = opt.get_text(strip=True)
            
            if value and value.startswith('http') and value not in seen:
                # Clean up the text (remove leading dashes)
                text = re.sub(r'^-+\s*', '', text).strip()
                if text and text != 'Navigate to:':
                    links.append({
                        'title': text,
                        'url': value,
                        'type': 'related_page'
                    })
                    seen.add(value)
    
    return links


async def get_bibliography(url: str) -> dict[str, Any]:
    """Get bibliography data from a Nobel Prize bibliography page."""
    status, content = await fetch_page(url)
    
    if status != 200:
        return {
            "success": False,
            "error": f"Failed to fetch page: HTTP {status}",
            "url": url
        }
    
    if not content:
        return {
            "success": False,
            "error": "No content received",
            "url": url
        }
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # Determine page type based on URL and content
    url_lower = url.lower()
    is_table_format = '/bibliography/' in url_lower and '/bio-bibliography/' not in url_lower
    
    # Check for tables in content
    tables = soup.find_all('table')
    
    # Extract data
    metadata = extract_metadata(soup)
    related_links = extract_related_links(soup, url)
    
    if tables and is_table_format:
        # Individual laureate bibliography (table format)
        bibliography = extract_table_bibliography(soup)
        page_type = "laureate_bibliography"
        biography = None
    else:
        # Bio-bibliography format (paragraphs)
        data = extract_bio_bibliography_text(soup)
        bibliography = {k: v for k, v in data.items() if k != 'biography'}
        biography = data.get('biography')
        if isinstance(biography, list) and biography:
            biography = '\n\n'.join(biography)
        else:
            biography = None
        page_type = "bio_bibliography"
    
    return {
        "success": True,
        "url": url,
        "page_type": page_type,
        "metadata": metadata,
        "biography": biography,
        "bibliography": bibliography,
        "related_links": related_links,
        "total_entries": bibliography.get('total_entries', 0)
    }


async def get_biblio_summary(url: str) -> dict[str, Any]:
    """Get a summary of bibliography entries (title, year, section) without full details."""
    full_data = await get_bibliography(url)
    
    if not full_data.get('success'):
        return full_data
    
    # Simplify the bibliography to just title, year, section
    summary: dict[str, Any] = {
        "success": True,
        "url": full_data['url'],
        "page_type": full_data['page_type'],
        "metadata": full_data['metadata'],
        "total_entries": full_data['total_entries'],
        "entries": []
    }
    
    bibliography = full_data.get('bibliography', {})
    
    # Handle table format (sections array)
    for section in bibliography.get('sections', []):
        section_name = section.get('name', 'Unknown')
        for entry in section.get('entries', []):
            summary['entries'].append({
                'title': entry.get('title', ''),
                'year': entry.get('year'),
                'section': section_name
            })
    
    # Handle bio-bibliography format (dictionary)
    for section_key, section_data in bibliography.items():
        if section_key in ['biography', 'total_entries', 'sections']:
            continue
        if isinstance(section_data, dict) and 'entries' in section_data:
            section_name = section_data.get('name', section_key)
            for entry in section_data.get('entries', []):
                summary['entries'].append({
                    'title': entry.get('title', ''),
                    'year': entry.get('year'),
                    'section': section_name
                })
    
    return summary


async def search_entries(url: str, query: str) -> dict[str, Any]:
    """Search for bibliography entries matching a query."""
    full_data = await get_bibliography(url)
    
    if not full_data.get('success'):
        return full_data
    
    query_lower = query.lower()
    matches: list[dict[str, Any]] = []
    
    bibliography = full_data.get('bibliography', {})
    
    # Search in table format sections
    for section in bibliography.get('sections', []):
        section_name = section.get('name', 'Unknown')
        for entry in section.get('entries', []):
            # Search in all text fields
            searchable = ' '.join([
                str(v) for v in entry.values() if isinstance(v, str)
            ]).lower()
            
            if query_lower in searchable:
                match = dict(entry)
                match['section'] = section_name
                matches.append(match)
    
    # Search in bio-bibliography format
    for section_key, section_data in bibliography.items():
        if section_key in ['biography', 'total_entries', 'sections']:
            continue
        if isinstance(section_data, dict) and 'entries' in section_data:
            section_name = section_data.get('name', section_key)
            for entry in section_data.get('entries', []):
                searchable = ' '.join([
                    str(v) for v in entry.values() if isinstance(v, str)
                ]).lower()
                
                if query_lower in searchable:
                    match = dict(entry)
                    match['section'] = section_name
                    matches.append(match)
    
    return {
        "success": True,
        "url": url,
        "query": query,
        "total_matches": len(matches),
        "matches": matches
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the Nobel Prize bibliography skill.
    
    Parameters:
        function: The function to execute
            - get_bibliography: Get full structured bibliography data
            - get_summary: Get summary list of entries (title, year, section)
            - search_entries: Search for entries matching a query
        url: The Nobel Prize URL to process
        query: Search query (required for search_entries function)
    
    Returns:
        Structured data based on the function called
    """
    func = params.get('function', 'get_bibliography')
    url = params.get('url')
    
    if not url:
        return {
            "success": False,
            "error": "URL parameter is required"
        }
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.netloc != 'www.nobelprize.org':
        return {
            "success": False,
            "error": "URL must be from www.nobelprize.org"
        }
    
    if '/bibliography/' not in url.lower() and '/bio-bibliography/' not in url.lower():
        return {
            "success": False,
            "error": "URL must be a bibliography or bio-bibliography page"
        }
    
    if func == 'get_bibliography':
        return await get_bibliography(url)
    elif func == 'get_summary':
        return await get_biblio_summary(url)
    elif func == 'search_entries':
        query = params.get('query')
        if not query:
            return {
                "success": False,
                "error": "Query parameter is required for search_entries"
            }
        return await search_entries(url, query)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {func}. Available: get_bibliography, get_summary, search_entries"
        }