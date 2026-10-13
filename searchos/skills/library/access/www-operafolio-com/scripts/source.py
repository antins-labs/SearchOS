"""
OperaFolio.com Access Skill

Fetches structured opera data from operafolio.com including:
- List of operas by composer
- Opera details (synopsis, arias, performance info)
- Composer information
- List of all composers
- List of all operas
- Famous arias
"""

from __future__ import annotations
import re
from typing import Any
from urllib.parse import quote
import aiohttp


BASE_URL = "http://www.operafolio.com"


def _normalize_name(name: str) -> str:
    """Convert a name to URL format (underscores instead of spaces)."""
    return name.replace(" ", "_")


def _parse_stars(html: str) -> int:
    """Extract star rating from HTML (0-3 stars)."""
    if 'star3.gif' in html:
        return 3
    elif 'star2.gif' in html:
        return 2
    elif 'star1.gif' in html:
        return 1
    return 0


def _extract_country(html: str) -> str | None:
    """Extract country code from country flag image."""
    match = re.search(r'country/([A-Z]{2})\.gif', html)
    return match.group(1) if match else None


def _clean_text(text: str) -> str:
    """Clean up text by removing extra whitespace."""
    return re.sub(r'\s+', ' ', text).strip()


def _decode_html_entities(text: str) -> str:
    """Decode common HTML entities."""
    entities = {
        '&#233;': 'é',
        '&#232;': 'è',
        '&#234;': 'ê',
        '&#235;': 'ë',
        '&#224;': 'à',
        '&#226;': 'â',
        '&#244;': 'ô',
        '&#238;': 'î',
        '&#239;': 'ï',
        '&#231;': 'ç',
        '&#242;': 'ò',
        '&#243;': 'ó',
        '&#246;': 'ö',
        '&#252;': 'ü',
        '&#228;': 'ä',
        '&#251;': 'û',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    return text


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        response.raise_for_status()
        return await response.text()


async def _get_composer_operas(composer: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch list of operas by a specific composer."""
    composer_param = _normalize_name(composer)
    url = f"{BASE_URL}/list_of_operas.asp?n={composer_param}"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to fetch composer operas: {str(e)}", "url": url}
    
    operas = []
    
    # Parse composer info
    composer_name = composer.replace("_", " ")
    years_match = re.search(r'(\d{4})\s*-\s*(\d{4})', html)
    years = f"{years_match.group(1)} - {years_match.group(2)}" if years_match else None
    country = _extract_country(html)
    rating = _parse_stars(html)
    
    # Find the ordered list of operas
    ol_match = re.search(r'<ol>(.*?)</ol>', html, re.DOTALL)
    if ol_match:
        ol_content = ol_match.group(1)
        
        # Split by list items - improved pattern
        items = re.split(r'</li>\s*(?:<li|$)', ol_content)
        
        for item in items:
            if not item.strip():
                continue
            # Add back the <li> if it was stripped
            if not item.startswith('<li'):
                item = '<li>' + item
            
            opera = {}
            
            # Extract opera name and link
            name_match = re.search(r'<a href="opera\.asp\?n=([^"]+)">([^<]+)</a>', item)
            if name_match:
                opera["url_name"] = name_match.group(1)
                opera["name"] = _clean_text(name_match.group(2))
            else:
                # Some operas may not have links (alternate versions)
                # Get text before any <ul> tag
                text_before_ul = re.sub(r'<ul>.*', '', item, flags=re.DOTALL)
                text_before_ul = re.sub(r'<[^>]+>', ' ', text_before_ul)
                text_before_ul = _clean_text(text_before_ul)
                if text_before_ul and text_before_ul != '-':
                    # Extract name (first part before dash)
                    parts = text_before_ul.split(' - ')
                    if parts and parts[0].strip():
                        opera["name"] = parts[0].strip()
            
            # Extract acts
            acts_match = re.search(r'(\d+)\s*acts?', item)
            if acts_match:
                opera["acts"] = int(acts_match.group(1))
            
            # Check for Grand opéra
            if 'Grand opéra' in item:
                opera["genre"] = "Grand opéra"
            
            # Extract language
            lang_match = re.search(r'-\s*(Italian|French|German|English|Russian|Spanish|Czech)\s*(?:<ul|<|$)', item)
            if lang_match:
                opera["language"] = lang_match.group(1)
            
            # Extract librettist
            lib_match = re.search(r'Libretto by ([^<]+)', item)
            if lib_match:
                opera["librettist"] = _clean_text(lib_match.group(1))
            
            # Extract first performance
            perf_match = re.search(r'First performance at ([^<]+)', item)
            if perf_match:
                perf_text = _clean_text(perf_match.group(1))
                # Extract year from performance info
                year_match = re.search(r'(?:in\s+)?(\d{4})(?:\s|$)', perf_text)
                if year_match:
                    opera["year"] = int(year_match.group(1))
                opera["first_performance"] = perf_text
            
            # Extract rating for this opera
            opera["rating"] = _parse_stars(item)
            
            if opera.get("name"):
                operas.append(opera)
    
    return {
        "composer": {
            "name": composer_name,
            "years": years,
            "country": country,
            "rating": rating
        },
        "operas": operas,
        "count": len(operas),
        "url": url
    }


async def _get_opera_details(opera: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch detailed information about a specific opera."""
    opera_param = _normalize_name(opera)
    url = f"{BASE_URL}/opera.asp?n={opera_param}"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to fetch opera details: {str(e)}", "url": url}
    
    result = {"url": url}
    
    # Extract title from page title
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        result["title"] = title_match.group(1).split(" - ")[0].strip()
    
    # Extract opera name and year from the header row
    # Pattern: bgcolor="lightblue" colspan="2">Rigoletto <img src="country/IT.gif"...> - 1851 <img...
    header_match = re.search(r'bgcolor="lightblue"[^>]*>([A-Za-z][^<]*?)\s*<img src="country/([A-Z]{2})\.gif[^>]*>\s*-\s*(\d{4})', html)
    if header_match:
        result["name"] = _clean_text(header_match.group(1))
        result["country"] = header_match.group(2)
        result["year"] = int(header_match.group(3))
    else:
        # Fallback: just extract name
        name_match = re.search(r'bgcolor="lightblue"[^>]*>\s*([A-Za-z][^<]*?)\s*(?:<|$)', html)
        if name_match:
            result["name"] = _clean_text(name_match.group(1))
        result["country"] = _extract_country(html)
    
    # Extract rating
    result["rating"] = _parse_stars(html)
    
    # Extract composer link and name
    composer_match = re.search(r'<a href="composer\.asp\?n=([^"]+)">([^<]+)</a>', html)
    if composer_match:
        result["composer_url_name"] = composer_match.group(1)
        result["composer"] = composer_match.group(2)
    
    # Extract librettist
    lib_match = re.search(r'Libretto by ([^<]+)', html)
    if lib_match:
        result["librettist"] = _clean_text(lib_match.group(1))
    
    # Extract first performance
    perf_match = re.search(r'First performance at ([^<]+)', html)
    if perf_match:
        result["first_performance"] = _clean_text(perf_match.group(1))
    
    # Extract genre (from acts info or genre labels)
    genre_patterns = [
        r'Grand opéra',
        r'Opera buffa',
        r'Opera seria',
        r'Verismo',
        r'Singspiel',
        r'Opéra comique',
        r'Melodramma giocoso',
        r'Opérette',
        r'Dramma lirico',
        r'Opera semiseria',
    ]
    for pattern in genre_patterns:
        if re.search(pattern, html, re.IGNORECASE):
            result["genre"] = re.search(pattern, html, re.IGNORECASE).group(0)
            break
    
    # Extract synopsis - look for content after Synopsis anchor
    synopsis_match = re.search(r'<a name="#Synopsis">Synopsis</a>.*?<tr>\s*<td colspan="2">(.*?)</td>\s*</tr>', html, re.DOTALL)
    if synopsis_match:
        synopsis = synopsis_match.group(1)
        # Clean up HTML tags
        synopsis = re.sub(r'<br\s*/?>', '\n', synopsis)
        synopsis = re.sub(r'<[^>]+>', '', synopsis)
        synopsis = _clean_text(synopsis)
        if synopsis:
            result["synopsis"] = synopsis
    
    # Extract arias
    arias = []
    aria_section = re.search(r'<a name="#Arias">Arias</a>.*?<ol>(.*?)</ol>', html, re.DOTALL)
    if aria_section:
        aria_items = re.findall(r'<li>(.*?)</li>', aria_section.group(1), re.DOTALL)
        for item in aria_items:
            aria = {}
            aria_match = re.search(r'<a href="aria\.asp\?n=([^"]+)">([^<]+)</a>', item)
            if aria_match:
                aria["url_name"] = aria_match.group(1)
                aria["name"] = _clean_text(aria_match.group(2))
            
            # Extract character/voice type (appears after the aria name)
            char_match = re.search(r'</a>\s*-\s*([^<]+)', item)
            if char_match:
                aria["character"] = _clean_text(char_match.group(1))
            
            aria["rating"] = _parse_stars(item)
            
            if aria.get("name"):
                arias.append(aria)
    
    if arias:
        result["arias"] = arias
    
    # Extract external links (libretto, Wikipedia, etc.)
    links = {}
    
    # Italian libretto
    it_lib = re.search(r'<a href="(http://www\.giuseppeverdi\.it/[^"]+)"[^>]*>Italian libretto</a>', html)
    if it_lib:
        links["italian_libretto"] = it_lib.group(1)
    
    # Wikipedia
    wiki = re.search(r'<a href="(http://en\.wikipedia\.org/wiki/[^"]+)"[^>]*>Article in Wikipedia</a>', html)
    if wiki:
        links["wikipedia"] = wiki.group(1)
    
    # OperaBase (upcoming performances)
    operabase = re.search(r'<a href="(http://www\.operabase\.com/[^"]+)"[^>]*>Upcoming Performances</a>', html)
    if operabase:
        links["upcoming_performances"] = operabase.group(1)
    
    if links:
        result["external_links"] = links
    
    # Extract background facts
    facts = []
    facts_match = re.search(r'Background Facts.*?<ul>(.*?)</ul>', html, re.DOTALL)
    if facts_match:
        fact_items = re.findall(r'<li>([^<]+)</li>', facts_match.group(1))
        for fact in fact_items:
            facts.append(_clean_text(fact))
    if facts:
        result["background_facts"] = facts
    
    return result


async def _get_composers_list(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch list of all composers."""
    url = f"{BASE_URL}/index.asp?o=x"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to fetch composers list: {str(e)}", "url": url}
    
    composers = []
    
    # Find all composer entries
    pattern = r'<a href="composer\.asp\?n=([^"]+)">([^<]+)</a>\s*\((\d+)-(\d+)\)\s*<img src="symbols/star(\d)\.gif"'
    
    for match in re.finditer(pattern, html):
        composers.append({
            "url_name": match.group(1),
            "name": match.group(2),
            "birth_year": int(match.group(3)),
            "death_year": int(match.group(4)),
            "rating": int(match.group(5))
        })
    
    return {
        "composers": composers,
        "count": len(composers),
        "url": url
    }


async def _get_operas_list(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch list of featured operas."""
    url = f"{BASE_URL}/operas.asp"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to fetch operas list: {str(e)}", "url": url}
    
    operas = []
    
    # Find all opera entries - updated pattern to capture genre
    pattern = r'<a href="opera\.asp\?n=([^"]+)">([^<]+)</a>\s*\(<a href="composer\.asp\?n=([^"]+)">([^<]+)</a>\)\s*<img src="country/([A-Z]{2})\.gif"[^>]*>\s*-\s*(\d{4})\s*<img src="symbols/star(\d)\.gif"[^>]*(?:>\s*-\s*([^<]+))?'
    
    for match in re.finditer(pattern, html):
        opera = {
            "url_name": match.group(1),
            "name": _decode_html_entities(match.group(2)),
            "composer_url_name": match.group(3),
            "composer": match.group(4),
            "country": match.group(5),
            "year": int(match.group(6)),
            "rating": int(match.group(7))
        }
        # Genre is in group 8 if present
        if len(match.groups()) >= 8 and match.group(8):
            opera["genre"] = _clean_text(match.group(8))
        operas.append(opera)
    
    return {
        "operas": operas,
        "count": len(operas),
        "url": url
    }


async def _search_operas(query: str, session: aiohttp.ClientSession) -> dict[str, Any]:
    """Search for operas by name."""
    url = f"{BASE_URL}/operas.asp?s={quote(query)}"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to search operas: {str(e)}", "url": url}
    
    operas = []
    
    # Find all opera entries in search results
    pattern = r'<a href="opera\.asp\?n=([^"]+)">([^<]+)</a>\s*\(<a href="composer\.asp\?n=([^"]+)">([^<]+)</a>\)\s*<img src="country/([A-Z]{2})\.gif"[^>]*>\s*-\s*(\d{4})\s*<img src="symbols/star(\d)\.gif"'
    
    for match in re.finditer(pattern, html):
        operas.append({
            "url_name": match.group(1),
            "name": _decode_html_entities(match.group(2)),
            "composer_url_name": match.group(3),
            "composer": match.group(4),
            "country": match.group(5),
            "year": int(match.group(6)),
            "rating": int(match.group(7))
        })
    
    return {
        "query": query,
        "operas": operas,
        "count": len(operas),
        "url": url
    }


async def _get_famous_arias(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Fetch list of famous arias."""
    url = f"{BASE_URL}/arias.asp"
    
    try:
        html = await _fetch_html(session, url)
    except Exception as e:
        return {"error": f"Failed to fetch arias list: {str(e)}", "url": url}
    
    arias = []
    
    # Find all aria entries - updated pattern
    pattern = r'<td colspan="2">([^<]+(?:,\s*[^<]+)?),\s*<a href="opera\.asp\?n=([^"]+)">([^<]+)</a>\s*\(<a href="composer\.asp\?n=([^"]+)">([^<]+)</a>\)<img src="symbols/star(\d)\.gif"'
    
    for match in re.finditer(pattern, html):
        arias.append({
            "name": _clean_text(match.group(1)),
            "opera_url_name": match.group(2),
            "opera": match.group(3),
            "composer_url_name": match.group(4),
            "composer": match.group(5),
            "rating": int(match.group(6))
        })
    
    return {
        "arias": arias,
        "count": len(arias),
        "url": url
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute OperaFolio skill functions.
    
    Supported functions:
    - get_composer_operas: Get list of operas by composer (requires 'composer' param)
    - get_opera_details: Get detailed info about an opera (requires 'opera' param)
    - get_composers: Get list of all composers
    - get_operas: Get list of featured operas
    - search_operas: Search operas by name (requires 'query' param)
    - get_famous_arias: Get list of famous arias
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        if function == "get_composer_operas":
            composer = params.get("composer", "")
            if not composer:
                return {"error": "Missing required parameter: composer"}
            return await _get_composer_operas(composer, session)
        
        elif function == "get_opera_details":
            opera = params.get("opera", "")
            if not opera:
                return {"error": "Missing required parameter: opera"}
            return await _get_opera_details(opera, session)
        
        elif function == "get_composers":
            return await _get_composers_list(session)
        
        elif function == "get_operas":
            return await _get_operas_list(session)
        
        elif function == "search_operas":
            query = params.get("query", "")
            if not query:
                return {"error": "Missing required parameter: query"}
            return await _search_operas(query, session)
        
        elif function == "get_famous_arias":
            return await _get_famous_arias(session)
        
        else:
            return {"error": f"Unknown function: {function}"}