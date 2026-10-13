"""
RSC Periodic Table Element Data Access Skill

Fetches element data from the Royal Society of Chemistry Periodic Table.
URL format: https://periodic-table.rsc.org/element/{atomic_number}/{element_name}

HTML is server-side rendered with structured tables containing:
- Basic properties (Group, Period, Block, Atomic number, Mass, etc.)
- Discovery information (date, discoverers, name origin)
- Uses and properties content
- History content
- Atomic data (radii, electronegativity, ionisation energies)
- Oxidation states and isotopes
"""

import aiohttp
import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup


async def _fetch_element_page(atomic_number: int, element_name: str = None) -> tuple[int, str]:
    """Fetch the element page HTML. Returns (status_code, html)."""
    # RSC URLs use lowercase element names
    if element_name:
        element_name = element_name.lower()
    else:
        element_name = ""
    
    url = f"https://periodic-table.rsc.org/element/{atomic_number}/{element_name}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
            return resp.status, html, url


def _parse_basic_properties(soup: BeautifulSoup) -> dict:
    """Parse the main properties table (Group, Period, Atomic Number, etc.)."""
    props = {}
    
    table = soup.find('table', class_='element_hover_table_ca')
    if not table:
        return props
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        # Table has pairs of key-value in each row (4 cells per row typically)
        for i in range(0, len(cells), 2):
            if i + 1 < len(cells):
                key = cells[i].get_text(strip=True)
                val = cells[i + 1].get_text(strip=True)
                if key and val:
                    # Clean up key
                    key = re.sub(r'\s+', ' ', key)
                    props[key] = val
    
    return props


def _parse_discovery_info(soup: BeautifulSoup) -> dict:
    """Parse the discovery information table."""
    discovery = {}
    
    table = soup.find('table', class_='element_hover_table')
    if not table:
        return discovery
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)
            if key and val:
                discovery[key] = val
    
    return discovery


def _parse_section_content(soup: BeautifulSoup, section_id: str) -> list[str]:
    """Parse content from an expandable section (uses, history, etc.)."""
    content = []
    
    section = soup.find('div', id=section_id)
    if not section:
        return content
    
    # Get all accordian_details divs
    details = section.find_all('div', class_='accordian_details')
    for d in details:
        text = d.get_text(strip=True)
        if text:
            content.append(text)
    
    return content


def _parse_atomic_data(soup: BeautifulSoup) -> dict:
    """Parse the atomic data table."""
    atomic_data = {}
    
    section = soup.find('div', id='exp_atomicdata')
    if not section:
        return atomic_data
    
    table = section.find('table', class_='atomic_data')
    if not table:
        return atomic_data
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        # Process pairs
        for i in range(0, len(cells), 2):
            if i + 1 < len(cells):
                key = cells[i].get_text(strip=True)
                val = cells[i + 1].get_text(strip=True)
                if key and val:
                    key = re.sub(r'\s+', ' ', key)
                    atomic_data[key] = val
    
    return atomic_data


def _parse_oxidation_isotopes(soup: BeautifulSoup) -> dict:
    """Parse oxidation states and isotopes table."""
    result = {
        "oxidation_states": None,
        "isotopes": []
    }
    
    section = soup.find('div', id='exp_oxidation')
    if not section:
        return result
    
    table = section.find('table', class_='oxidation_table')
    if not table:
        return result
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        texts = [c.get_text(strip=True) for c in cells]
        
        # First row is oxidation states
        if 'oxidation states' in ' '.join(texts).lower():
            if len(texts) >= 2:
                result["oxidation_states"] = texts[-1] if texts[-1] != texts[0] else None
        # Isotope rows have 6 columns: empty, isotope, mass, abundance, half_life, decay
        elif len(texts) >= 5 and texts[0] == '':
            isotope = {
                "isotope": texts[1] if len(texts) > 1 else None,
                "atomic_mass": texts[2] if len(texts) > 2 else None,
                "natural_abundance": texts[3] if len(texts) > 3 else None,
                "half_life": texts[4] if len(texts) > 4 else None,
                "decay_mode": texts[5] if len(texts) > 5 else None
            }
            # Clean up None/empty values
            isotope = {k: v for k, v in isotope.items() if v and v != '-'}
            if isotope.get('isotope'):
                result["isotopes"].append(isotope)
    
    return result


def _extract_element_symbol(soup: BeautifulSoup) -> str:
    """Extract element symbol from the page."""
    # Look for symbol in various places
    # The symbol is typically shown prominently near the element name
    
    # Method 1: Look in the TopCard popup which has format "Mt Meitnerium 109 [278]"
    top_card = soup.find('div', id='TopCard_popup_div')
    if top_card:
        text = top_card.get_text()
        # Symbol is typically a 1-2 letter code followed by element name
        match = re.search(r'\b([A-Z][a-z]?)\s+[A-Z][a-z]+', text)
        if match:
            return match.group(1)
    
    # Method 2: Extract from image alt text or src
    img = soup.find('img', alt=re.compile(r'Element', re.I))
    if img and img.get('alt'):
        match = re.search(r'([A-Z][a-z]?)\s+Element', img.get('alt', ''))
        if match:
            return match.group(1)
    
    # Method 3: From the properties table - electron configuration often shows symbol
    props = _parse_basic_properties(soup)
    if 'Electron configuration' in props:
        # This doesn't give us the symbol, but we can try another approach
        pass
    
    return None


async def get_element(atomic_number: int, element_name: str = None) -> dict:
    """
    Fetch complete element data from RSC Periodic Table.
    
    Args:
        atomic_number: The atomic number of the element (1-118)
        element_name: Optional element name (will be lowercased). If not provided,
                      the URL will still work with just the atomic number.
    
    Returns:
        Dictionary with all element data or error information.
    """
    try:
        status, html, url = await _fetch_element_page(atomic_number, element_name)
        
        if status != 200:
            return {
                "error": f"HTTP error {status}",
                "status_code": status,
                "url": url
            }
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if we got a valid element page
        name_elem = soup.find('span', class_='element_header')
        if not name_elem:
            return {
                "error": "Element not found or page structure changed",
                "status_code": status,
                "url": url
            }
        
        element_name_actual = name_elem.get_text(strip=True)
        
        # Parse all data sections
        basic_props = _parse_basic_properties(soup)
        discovery = _parse_discovery_info(soup)
        uses = _parse_section_content(soup, 'exp_uses')
        history = _parse_section_content(soup, 'exp_history')
        atomic_data = _parse_atomic_data(soup)
        oxidation_isotopes = _parse_oxidation_isotopes(soup)
        
        # Extract symbol - try from basic props or derive from name
        symbol = _extract_element_symbol(soup)
        if not symbol and 'Key isotopes' in basic_props:
            # Key isotopes format is like "276Mt" - extract symbol
            match = re.search(r'\d*([A-Z][a-z]?)$', basic_props.get('Key isotopes', ''))
            if match:
                symbol = match.group(1)
        
        # Build result
        result = {
            "name": element_name_actual,
            "symbol": symbol,
            "url": url,
            "atomic_number": atomic_number,
            "properties": {},
            "discovery": {},
            "uses": [],
            "history": [],
            "atomic_data": {},
            "oxidation_states": None,
            "isotopes": []
        }
        
        # Map basic properties to structured fields
        prop_mapping = {
            'Group': 'group',
            'Period': 'period',
            'Block': 'block',
            'Atomic number': 'atomic_number',
            'Relative atomic mass': 'atomic_mass',
            'State at 20°C': 'state_at_20c',
            'Melting point': 'melting_point',
            'Boiling point': 'boiling_point',
            'Density (g cm−3)': 'density',
            'Electron configuration': 'electron_configuration',
            'CAS number': 'cas_number',
            'ChemSpider ID': 'chemspider_id',
            'Key isotopes': 'key_isotopes'
        }
        
        for key, val in basic_props.items():
            clean_key = prop_mapping.get(key, key.lower().replace(' ', '_').replace('(', '').replace(')', ''))
            result["properties"][clean_key] = val
        
        # Map discovery info
        disc_mapping = {
            'Discovery date': 'date',
            'Discovered by': 'discoverers',
            'Origin of the name': 'name_origin',
            'Allotropes': 'allotropes'
        }
        
        for key, val in discovery.items():
            clean_key = disc_mapping.get(key, key.lower().replace(' ', '_'))
            result["discovery"][clean_key] = val
        
        # Add uses, history
        result["uses"] = uses
        result["history"] = history
        
        # Add atomic data
        atomic_mapping = {
            'Atomic radius, non-bonded (Å)': 'atomic_radius_non_bonded',
            'Covalent radius (Å)': 'covalent_radius',
            'Electron affinity (kJ mol−1)': 'electron_affinity',
            'Electronegativity (Pauling scale)': 'electronegativity',
            'Ionisation energies (kJ mol−1)': 'ionisation_energies'
        }
        
        for key, val in atomic_data.items():
            clean_key = atomic_mapping.get(key, key.lower().replace(' ', '_').replace('(', '').replace(')', ''))
            result["atomic_data"][clean_key] = val
        
        # Add oxidation states and isotopes
        result["oxidation_states"] = oxidation_isotopes.get("oxidation_states")
        result["isotopes"] = oxidation_isotopes.get("isotopes", [])
        
        return result
        
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "url": f"https://periodic-table.rsc.org/element/{atomic_number}/{element_name or ''}"
        }
    except Exception as e:
        return {
            "error": f"Parse error: {str(e)}",
            "url": f"https://periodic-table.rsc.org/element/{atomic_number}/{element_name or ''}"
        }


async def search_element(query: str) -> dict:
    """
    Search for an element by name or symbol.
    Returns element data if found.
    
    Args:
        query: Element name, symbol, or atomic number (as string)
    
    Returns:
        Element data dictionary or error
    """
    query = query.strip().lower()
    
    # Element data for lookup
    elements = {
        'h': (1, 'hydrogen'), 'hydrogen': (1, 'hydrogen'),
        'he': (2, 'helium'), 'helium': (2, 'helium'),
        'li': (3, 'lithium'), 'lithium': (3, 'lithium'),
        'be': (4, 'beryllium'), 'beryllium': (4, 'beryllium'),
        'b': (5, 'boron'), 'boron': (5, 'boron'),
        'c': (6, 'carbon'), 'carbon': (6, 'carbon'),
        'n': (7, 'nitrogen'), 'nitrogen': (7, 'nitrogen'),
        'o': (8, 'oxygen'), 'oxygen': (8, 'oxygen'),
        'f': (9, 'fluorine'), 'fluorine': (9, 'fluorine'),
        'ne': (10, 'neon'), 'neon': (10, 'neon'),
        'na': (11, 'sodium'), 'sodium': (11, 'sodium'),
        'mg': (12, 'magnesium'), 'magnesium': (12, 'magnesium'),
        'al': (13, 'aluminium'), 'aluminium': (13, 'aluminium'), 'aluminum': (13, 'aluminium'),
        'si': (14, 'silicon'), 'silicon': (14, 'silicon'),
        'p': (15, 'phosphorus'), 'phosphorus': (15, 'phosphorus'),
        's': (16, 'sulfur'), 'sulfur': (16, 'sulfur'), 'sulphur': (16, 'sulfur'),
        'cl': (17, 'chlorine'), 'chlorine': (17, 'chlorine'),
        'ar': (18, 'argon'), 'argon': (18, 'argon'),
        'k': (19, 'potassium'), 'potassium': (19, 'potassium'),
        'ca': (20, 'calcium'), 'calcium': (20, 'calcium'),
        'sc': (21, 'scandium'), 'scandium': (21, 'scandium'),
        'ti': (22, 'titanium'), 'titanium': (22, 'titanium'),
        'v': (23, 'vanadium'), 'vanadium': (23, 'vanadium'),
        'cr': (24, 'chromium'), 'chromium': (24, 'chromium'),
        'mn': (25, 'manganese'), 'manganese': (25, 'manganese'),
        'fe': (26, 'iron'), 'iron': (26, 'iron'),
        'co': (27, 'cobalt'), 'cobalt': (27, 'cobalt'),
        'ni': (28, 'nickel'), 'nickel': (28, 'nickel'),
        'cu': (29, 'copper'), 'copper': (29, 'copper'),
        'zn': (30, 'zinc'), 'zinc': (30, 'zinc'),
        'ga': (31, 'gallium'), 'gallium': (31, 'gallium'),
        'ge': (32, 'germanium'), 'germanium': (32, 'germanium'),
        'as': (33, 'arsenic'), 'arsenic': (33, 'arsenic'),
        'se': (34, 'selenium'), 'selenium': (34, 'selenium'),
        'br': (35, 'bromine'), 'bromine': (35, 'bromine'),
        'kr': (36, 'krypton'), 'krypton': (36, 'krypton'),
        'rb': (37, 'rubidium'), 'rubidium': (37, 'rubidium'),
        'sr': (38, 'strontium'), 'strontium': (38, 'strontium'),
        'y': (39, 'yttrium'), 'yttrium': (39, 'yttrium'),
        'zr': (40, 'zirconium'), 'zirconium': (40, 'zirconium'),
        'nb': (41, 'niobium'), 'niobium': (41, 'niobium'),
        'mo': (42, 'molybdenum'), 'molybdenum': (42, 'molybdenum'),
        'tc': (43, 'technetium'), 'technetium': (43, 'technetium'),
        'ru': (44, 'ruthenium'), 'ruthenium': (44, 'ruthenium'),
        'rh': (45, 'rhodium'), 'rhodium': (45, 'rhodium'),
        'pd': (46, 'palladium'), 'palladium': (46, 'palladium'),
        'ag': (47, 'silver'), 'silver': (47, 'silver'),
        'cd': (48, 'cadmium'), 'cadmium': (48, 'cadmium'),
        'in': (49, 'indium'), 'indium': (49, 'indium'),
        'sn': (50, 'tin'), 'tin': (50, 'tin'),
        'sb': (51, 'antimony'), 'antimony': (51, 'antimony'),
        'te': (52, 'tellurium'), 'tellurium': (52, 'tellurium'),
        'i': (53, 'iodine'), 'iodine': (53, 'iodine'),
        'xe': (54, 'xenon'), 'xenon': (54, 'xenon'),
        'cs': (55, 'caesium'), 'caesium': (55, 'caesium'), 'cesium': (55, 'caesium'),
        'ba': (56, 'barium'), 'barium': (56, 'barium'),
        'la': (57, 'lanthanum'), 'lanthanum': (57, 'lanthanum'),
        'ce': (58, 'cerium'), 'cerium': (58, 'cerium'),
        'pr': (59, 'praseodymium'), 'praseodymium': (59, 'praseodymium'),
        'nd': (60, 'neodymium'), 'neodymium': (60, 'neodymium'),
        'pm': (61, 'promethium'), 'promethium': (61, 'promethium'),
        'sm': (62, 'samarium'), 'samarium': (62, 'samarium'),
        'eu': (63, 'europium'), 'europium': (63, 'europium'),
        'gd': (64, 'gadolinium'), 'gadolinium': (64, 'gadolinium'),
        'tb': (65, 'terbium'), 'terbium': (65, 'terbium'),
        'dy': (66, 'dysprosium'), 'dysprosium': (66, 'dysprosium'),
        'ho': (67, 'holmium'), 'holmium': (67, 'holmium'),
        'er': (68, 'erbium'), 'erbium': (68, 'erbium'),
        'tm': (69, 'thulium'), 'thulium': (69, 'thulium'),
        'yb': (70, 'ytterbium'), 'ytterbium': (70, 'ytterbium'),
        'lu': (71, 'lutetium'), 'lutetium': (71, 'lutetium'),
        'hf': (72, 'hafnium'), 'hafnium': (72, 'hafnium'),
        'ta': (73, 'tantalum'), 'tantalum': (73, 'tantalum'),
        'w': (74, 'tungsten'), 'tungsten': (74, 'tungsten'), 'wolfram': (74, 'tungsten'),
        're': (75, 'rhenium'), 'rhenium': (75, 'rhenium'),
        'os': (76, 'osmium'), 'osmium': (76, 'osmium'),
        'ir': (77, 'iridium'), 'iridium': (77, 'iridium'),
        'pt': (78, 'platinum'), 'platinum': (78, 'platinum'),
        'au': (79, 'gold'), 'gold': (79, 'gold'),
        'hg': (80, 'mercury'), 'mercury': (80, 'mercury'),
        'tl': (81, 'thallium'), 'thallium': (81, 'thallium'),
        'pb': (82, 'lead'), 'lead': (82, 'lead'),
        'bi': (83, 'bismuth'), 'bismuth': (83, 'bismuth'),
        'po': (84, 'polonium'), 'polonium': (84, 'polonium'),
        'at': (85, 'astatine'), 'astatine': (85, 'astatine'),
        'rn': (86, 'radon'), 'radon': (86, 'radon'),
        'fr': (87, 'francium'), 'francium': (87, 'francium'),
        'ra': (88, 'radium'), 'radium': (88, 'radium'),
        'ac': (89, 'actinium'), 'actinium': (89, 'actinium'),
        'th': (90, 'thorium'), 'thorium': (90, 'thorium'),
        'pa': (91, 'protactinium'), 'protactinium': (91, 'protactinium'),
        'u': (92, 'uranium'), 'uranium': (92, 'uranium'),
        'np': (93, 'neptunium'), 'neptunium': (93, 'neptunium'),
        'pu': (94, 'plutonium'), 'plutonium': (94, 'plutonium'),
        'am': (95, 'americium'), 'americium': (95, 'americium'),
        'cm': (96, 'curium'), 'curium': (96, 'curium'),
        'bk': (97, 'berkelium'), 'berkelium': (97, 'berkelium'),
        'cf': (98, 'californium'), 'californium': (98, 'californium'),
        'es': (99, 'einsteinium'), 'einsteinium': (99, 'einsteinium'),
        'fm': (100, 'fermium'), 'fermium': (100, 'fermium'),
        'md': (101, 'mendelevium'), 'mendelevium': (101, 'mendelevium'),
        'no': (102, 'nobelium'), 'nobelium': (102, 'nobelium'),
        'lr': (103, 'lawrencium'), 'lawrencium': (103, 'lawrencium'),
        'rf': (104, 'rutherfordium'), 'rutherfordium': (104, 'rutherfordium'),
        'db': (105, 'dubnium'), 'dubnium': (105, 'dubnium'),
        'sg': (106, 'seaborgium'), 'seaborgium': (106, 'seaborgium'),
        'bh': (107, 'bohrium'), 'bohrium': (107, 'bohrium'),
        'hs': (108, 'hassium'), 'hassium': (108, 'hassium'),
        'mt': (109, 'meitnerium'), 'meitnerium': (109, 'meitnerium'),
        'ds': (110, 'darmstadtium'), 'darmstadtium': (110, 'darmstadtium'),
        'rg': (111, 'roentgenium'), 'roentgenium': (111, 'roentgenium'),
        'cn': (112, 'copernicium'), 'copernicium': (112, 'copernicium'),
        'nh': (113, 'nihonium'), 'nihonium': (113, 'nihonium'),
        'fl': (114, 'flerovium'), 'flerovium': (114, 'flerovium'),
        'mc': (115, 'moscovium'), 'moscovium': (115, 'moscovium'),
        'lv': (116, 'livermorium'), 'livermorium': (116, 'livermorium'),
        'ts': (117, 'tennessine'), 'tennessine': (117, 'tennessine'),
        'og': (118, 'oganesson'), 'oganesson': (118, 'oganesson'),
    }
    
    # Try to parse as atomic number
    if query.isdigit():
        atomic_num = int(query)
        if 1 <= atomic_num <= 118:
            # Find element name for this atomic number
            for name, (num, elem_name) in elements.items():
                if num == atomic_num and len(name) > 2:  # Get full name, not symbol
                    return await get_element(atomic_num, elem_name)
            return await get_element(atomic_num)
        else:
            return {"error": f"Invalid atomic number: {query}. Must be 1-118."}
    
    # Try to find by name or symbol
    if query in elements:
        atomic_num, elem_name = elements[query]
        return await get_element(atomic_num, elem_name)
    
    # Try partial match
    for key, (atomic_num, elem_name) in elements.items():
        if key.startswith(query) or query in key:
            return await get_element(atomic_num, elem_name)
    
    return {"error": f"Element not found: {query}"}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the RSC Periodic Table skill.
    
    Functions:
        - get_element: Fetch element data by atomic number
        - search_element: Search for element by name, symbol, or atomic number
    """
    function = params.get("function", "")
    
    if function == "get_element":
        atomic_number = params.get("atomic_number")
        element_name = params.get("element_name")
        
        if not atomic_number:
            return {"error": "Missing required parameter: atomic_number"}
        
        try:
            atomic_number = int(atomic_number)
        except (ValueError, TypeError):
            return {"error": f"Invalid atomic_number: {atomic_number}. Must be an integer."}
        
        return await get_element(atomic_number, element_name)
    
    elif function == "search_element":
        query = params.get("query")
        if not query:
            return {"error": "Missing required parameter: query"}
        
        return await search_element(query)
    
    else:
        return {"error": f"Unknown function: {function}. Available: get_element, search_element"}