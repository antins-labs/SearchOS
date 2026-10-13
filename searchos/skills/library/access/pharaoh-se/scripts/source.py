"""
SearchOS Access Skill for pharaoh.se
Retrieves structured information about Ancient Egyptian pharaohs and dynasties.
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import json


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute pharaoh.se queries.
    
    Functions:
    - get_pharaoh: Get detailed info about a specific pharaoh
    - get_dynasty: Get list of pharaohs in a dynasty
    - list_dynasties: Get overview of all dynasties
    - list_pharaohs: Get list of all pharaohs
    """
    function = params.get("function", "")
    
    if function == "get_pharaoh":
        return await get_pharaoh(params)
    elif function == "get_dynasty":
        return await get_dynasty(params)
    elif function == "list_dynasties":
        return await list_dynasties(params)
    elif function == "list_pharaohs":
        return await list_pharaohs(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def _fetch_html(url: str) -> tuple[int, str]:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=30) as resp:
            html = await resp.text()
            return resp.status, html


def _parse_pharaoh_table(table) -> list[dict]:
    """Parse a pharaoh list table from dynasty pages."""
    pharaohs = []
    rows = table.find_all('tr')
    
    if not rows:
        return pharaohs
    
    # Get headers from first row
    header_row = rows[0]
    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
    
    # Parse data rows
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        pharaoh_data = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                header = headers[i]
                text = cell.get_text(strip=True)
                link = cell.find('a')
                
                if link:
                    pharaoh_data[header] = {
                        'name': text,
                        'url': link.get('href', '')
                    }
                else:
                    pharaoh_data[header] = text
        
        if pharaoh_data:
            pharaohs.append(pharaoh_data)
    
    return pharaohs


def _parse_king_list_table(table) -> list[dict]:
    """Parse king list comparison tables."""
    entries = []
    rows = table.find_all('tr')
    
    if not rows:
        return entries
    
    headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
    
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        entry = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                header = headers[i]
                text = cell.get_text(strip=True)
                entry[header] = text
        
        if entry:
            entries.append(entry)
    
    return entries


def _extract_titulary(article) -> dict:
    """Extract royal titulary information from pharaoh page."""
    titulary = {}
    
    # Find all hiero divs which contain name information
    hiero_divs = article.find_all('div', class_='hiero')
    
    for hiero in hiero_divs:
        parent = hiero.parent
        if not parent:
            continue
        
        # Get the label (e.g., "Throne name", "Birth name")
        label_div = parent.find('div', class_=lambda x: x and 'text-xs' in str(x) and 'uppercase' in str(x))
        if not label_div:
            continue
        
        label = label_div.get_text(strip=True).lower()
        
        # Get transliteration
        tlit_div = parent.find('div', class_='tlit')
        transliteration = tlit_div.get_text(strip=True) if tlit_div else ''
        
        # Get meaning/description
        meaning_div = parent.find('div', class_='pt-1')
        meaning = meaning_div.get_text(strip=True) if meaning_div else ''
        
        # Get hieroglyph text
        hieroglyph = hiero.get_text(strip=True)
        
        name_data = {
            'hieroglyph': hieroglyph,
            'transliteration': transliteration,
            'meaning': meaning
        }
        
        # Map to standard name types
        if 'throne' in label or 'prenomen' in label:
            titulary['throne_name'] = name_data
        elif 'birth' in label or 'nomen' in label:
            titulary['birth_name'] = name_data
        elif 'horus' in label:
            titulary['horus_name'] = name_data
        elif 'nebty' in label or 'two ladies' in label:
            titulary['nebty_name'] = name_data
        elif 'golden' in label or 'golden horus' in label:
            titulary['golden_horus_name'] = name_data
        else:
            titulary[label.replace(' ', '_')] = name_data
    
    return titulary


def _extract_reign_info(article) -> dict:
    """Extract reign information from info table."""
    reign_info = {}
    
    tables = article.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            text = cells[0].get_text(strip=True).lower() if cells else ''
            
            # Look for predecessor/successor
            if 'predecessor' in text:
                links = cells[0].find_all('a')
                if links:
                    reign_info['predecessor'] = [
                        {'name': a.get_text(strip=True), 'url': a.get('href', '')}
                        for a in links
                    ]
            
            if 'successor' in text:
                links = cells[0].find_all('a')
                if links:
                    reign_info['successor'] = [
                        {'name': a.get_text(strip=True), 'url': a.get('href', '')}
                        for a in links
                    ]
            
            # Look for reign duration
            if 'turin' in text or 'reign' in text:
                for cell in cells[1:]:
                    cell_text = cell.get_text(strip=True)
                    if cell_text and any(c.isdigit() for c in cell_text):
                        reign_info['reign_duration'] = cell_text
            
            # Check for "Reign of" row
            full_text = ' '.join([c.get_text(strip=True) for c in cells])
            if 'reign of' in full_text.lower():
                # Extract pharaoh name from this row
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    if cell_text.lower().startswith('reign of'):
                        reign_info['pharaoh_name'] = cell_text.replace('Reign of', '').strip()
    
    return reign_info


async def get_pharaoh(params: dict[str, Any]) -> dict[str, Any]:
    """Get detailed information about a specific pharaoh."""
    pharaoh_slug = params.get("pharaoh_slug", "")
    
    if not pharaoh_slug:
        return {"error": "Missing required parameter: pharaoh_slug"}
    
    # Normalize slug (remove trailing slash if present)
    pharaoh_slug = pharaoh_slug.strip('/')
    
    url = f"https://pharaoh.se/ancient-egypt/pharaoh/{pharaoh_slug}"
    
    try:
        status, html = await _fetch_html(url)
        
        if status == 404:
            return {"error": f"Pharaoh not found: {pharaoh_slug}", "status": 404}
        elif status != 200:
            return {"error": f"HTTP error {status}", "status": status}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article')
        
        if not article:
            return {"error": "Could not find article content", "status": 200}
        
        # Extract basic info from JSON-LD
        json_ld = soup.find('script', type='application/ld+json')
        article_body = ""
        if json_ld:
            try:
                ld_data = json.loads(json_ld.string)
                article_body = ld_data.get('articleBody', '')
            except:
                pass
        
        # Get title
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else pharaoh_slug
        
        # Get introduction
        intro_div = article.find('div', class_='pb-6')
        introduction = intro_div.get_text(strip=True) if intro_div else ''
        
        # Extract titulary
        titulary = _extract_titulary(article)
        
        # Extract reign info
        reign_info = _extract_reign_info(article)
        
        # Get bibliography
        bibliography = []
        for h2 in article.find_all('h2'):
            if 'bibliography' in h2.get_text(strip=True).lower():
                ul = h2.find_next('ul')
                if ul:
                    for li in ul.find_all('li'):
                        bibliography.append(li.get_text(strip=True))
        
        # Get sections
        sections = {}
        for h2 in article.find_all('h2'):
            section_title = h2.get_text(strip=True)
            if section_title.lower() in ['bibliography']:
                continue
            
            section_content = []
            for sibling in h2.find_next_siblings():
                if sibling.name == 'h2':
                    break
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        section_content.append(text)
            
            if section_content:
                sections[section_title] = section_content
        
        return {
            "status": "success",
            "url": url,
            "pharaoh_slug": pharaoh_slug,
            "title": title,
            "introduction": introduction or article_body,
            "titulary": titulary,
            "reign_info": reign_info,
            "sections": sections,
            "bibliography": bibliography
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch pharaoh: {str(e)}"}


async def get_dynasty(params: dict[str, Any]) -> dict[str, Any]:
    """Get information about a specific dynasty including list of pharaohs."""
    dynasty_number = params.get("dynasty_number", "")
    
    if not dynasty_number:
        return {"error": "Missing required parameter: dynasty_number"}
    
    # Handle special cases like "predynastic"
    dynasty_number = str(dynasty_number).lower().strip('/')
    
    url = f"https://pharaoh.se/ancient-egypt/dynasty/{dynasty_number}/"
    
    try:
        status, html = await _fetch_html(url)
        
        if status == 404:
            return {"error": f"Dynasty not found: {dynasty_number}", "status": 404}
        elif status != 200:
            return {"error": f"HTTP error {status}", "status": status}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article')
        
        if not article:
            return {"error": "Could not find article content", "status": 200}
        
        # Get title
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else f"Dynasty {dynasty_number}"
        
        # Get introduction paragraphs
        paragraphs = []
        for p in article.find_all('p')[:5]:
            text = p.get_text(strip=True)
            if text and not text.startswith('Precedessor') and not text.startswith('Successor'):
                paragraphs.append(text)
        
        # Extract pharaoh tables
        pharaoh_lists = {}
        tables = article.find_all('table')
        
        for i, table in enumerate(tables):
            # Get table header/context
            header_row = table.find('tr')
            if not header_row:
                continue
            
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Determine table type
            if 'Pharaoh' in headers or 'pharaoh' in str(headers).lower():
                pharaohs = _parse_pharaoh_table(table)
                pharaoh_lists[f"pharaohs"] = pharaohs
            elif any('canon' in h.lower() or 'king list' in h.lower() or 'turin' in h.lower() or 'abydos' in h.lower() for h in headers):
                entries = _parse_king_list_table(table)
                list_name = ' '.join(headers[:2]) if len(headers) >= 2 else f"king_list_{i}"
                pharaoh_lists[list_name] = entries
            else:
                entries = _parse_king_list_table(table)
                pharaoh_lists[f"table_{i}"] = entries
        
        # Get sections
        sections = {}
        for h2 in article.find_all('h2'):
            section_title = h2.get_text(strip=True)
            
            section_content = []
            for sibling in h2.find_next_siblings():
                if sibling.name == 'h2':
                    break
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        section_content.append(text)
            
            if section_content:
                sections[section_title] = section_content
        
        return {
            "status": "success",
            "url": url,
            "dynasty_number": dynasty_number,
            "title": title,
            "introduction": paragraphs,
            "pharaoh_lists": pharaoh_lists,
            "sections": sections
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch dynasty: {str(e)}"}


async def list_dynasties(params: dict[str, Any]) -> dict[str, Any]:
    """Get overview of all dynasties."""
    url = "https://pharaoh.se/ancient-egypt/dynasties/"
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"HTTP error {status}", "status": status}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article')
        
        if not article:
            return {"error": "Could not find article content", "status": 200}
        
        # Extract dynasty tables
        dynasty_groups = {}
        tables = article.find_all('table')
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            if not rows:
                continue
            
            headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
            
            dynasties = []
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                dynasty_data = {}
                for j, cell in enumerate(cells):
                    if j < len(headers):
                        header = headers[j]
                        text = cell.get_text(strip=True)
                        link = cell.find('a')
                        
                        if link:
                            dynasty_data[header] = {
                                'name': text,
                                'url': link.get('href', '')
                            }
                        else:
                            dynasty_data[header] = text
                
                if dynasty_data:
                    dynasties.append(dynasty_data)
            
            # Use first dynasty's period as group name, or default
            group_name = f"period_{i+1}"
            if dynasties and 'Dynasty' in dynasties[0]:
                first = dynasties[0]['Dynasty']
                if isinstance(first, dict):
                    first_name = first.get('name', group_name)
                else:
                    first_name = str(first)
                
                # Determine period from dynasty number
                if any(d in first_name for d in ['1', '2']):
                    group_name = 'Early Dynastic / Old Kingdom'
                elif any(d in first_name for d in ['3', '4', '5', '6']):
                    group_name = 'Old Kingdom'
                elif any(d in first_name for d in ['7', '8', '9', '10', '11']):
                    group_name = 'First Intermediate Period'
                elif any(d in first_name for d in ['12']):
                    group_name = 'Middle Kingdom'
            
            dynasty_groups[group_name] = dynasties
        
        # Also get all dynasty links
        dynasty_links = []
        for link in article.find_all('a', href=lambda x: x and '/dynasty/' in x):
            dynasty_links.append({
                'name': link.get_text(strip=True),
                'url': link.get('href', '')
            })
        
        return {
            "status": "success",
            "url": url,
            "dynasty_groups": dynasty_groups,
            "all_dynasty_links": dynasty_links
        }
        
    except Exception as e:
        return {"error": f"Failed to list dynasties: {str(e)}"}


async def list_pharaohs(params: dict[str, Any]) -> dict[str, Any]:
    """Get list of all pharaohs."""
    url = "https://pharaoh.se/ancient-egypt/pharaohs/"
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"HTTP error {status}", "status": status}
        
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article')
        
        if not article:
            return {"error": "Could not find article content", "status": 200}
        
        # Extract all pharaoh links
        pharaohs = []
        seen = set()
        
        for link in article.find_all('a', href=lambda x: x and '/pharaoh/' in x):
            name = link.get_text(strip=True)
            href = link.get('href', '')
            
            # Deduplicate
            if href in seen:
                continue
            seen.add(href)
            
            pharaohs.append({
                'name': name,
                'slug': href.split('/pharaoh/')[-1].strip('/'),
                'url': href
            })
        
        # Get any introductory content
        intro_paragraphs = []
        for p in article.find_all('p')[:3]:
            text = p.get_text(strip=True)
            if text:
                intro_paragraphs.append(text)
        
        return {
            "status": "success",
            "url": url,
            "total_pharaohs": len(pharaohs),
            "introduction": intro_paragraphs,
            "pharaohs": pharaohs
        }
        
    except Exception as e:
        return {"error": f"Failed to list pharaohs: {str(e)}"}