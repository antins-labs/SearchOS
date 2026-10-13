"""
USGS Mineral Commodity Summaries PDF Extractor

Extracts structured mineral statistics from USGS Mineral Commodity Summaries publications.
Supports both individual commodity PDFs and the full annual report.
"""

import aiohttp
import io
import re
from typing import Any
from PyPDF2 import PdfReader


BASE_URL = "https://pubs.usgs.gov/periodicals/mcs2025"

# Commodity name to page number mapping (0-indexed) for the full MCS PDF
COMMODITY_PAGES = {
    "abrasives": 34, "aluminum": 35, "antimony": 37, "arsenic": 39,
    "asbestos": 41, "barite": 43, "bauxite and alumina": 45, "beryllium": 47,
    "bismuth": 49, "boron": 51, "bromine": 53, "cadmium": 55, "cement": 57,
    "cesium": 59, "chromium": 61, "clays": 63, "cobalt": 65, "copper": 67,
    "diamond": 70, "diatomite": 71, "feldspar and nepheline syenite": 73,
    "fluorspar": 75, "gallium": 77, "garnet": 79, "gemstones": 81,
    "germanium": 83, "gold": 85, "graphite": 87, "gypsum": 89, "hafnium": 91,
    "helium": 91, "indium": 93, "iodine": 95, "iron and steel": 97,
    "iron and steel scrap": 99, "iron and steel slag": 101, "iron ore": 103,
    "iron oxide pigments": 105, "kyanite and related minerals": 107,
    "lead": 109, "lime": 111, "lithium": 113, "magnesium": 117, "manganese": 119,
    "mercury": 121, "mica": 123, "molybdenum": 125, "nickel": 127, "niobium": 130,
    "nitrogen": 131, "palladium": 132, "peat": 133, "perlite": 135,
    "phosphate rock": 137, "platinum": 139, "platinum-group metals": 139,
    "potash": 141, "pumice and pumicite": 143, "quartz crystal": 145,
    "rare earths": 147, "rhenium": 149, "rubidium": 151, "salt": 153,
    "sand and gravel": 155, "scandium": 159, "selenium": 161, "silicon": 163,
    "silver": 165, "soda ash": 169, "stone": 171, "strontium": 173,
    "sulfur": 175, "talc": 177, "tantalum": 179, "tellurium": 181,
    "thallium": 183, "thorium": 185, "tin": 187, "titanium": 189,
    "trona": 191, "tungsten": 193, "vanadium": 195, "vermiculite": 197,
    "wollastonite": 199, "yttrium": 201, "zeolites": 203, "zinc": 205,
    "zirconium and hafnium": 207
}


async def fetch_pdf(url: str) -> bytes:
    """Download PDF content from URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def parse_salient_statistics(text: str) -> dict:
    """Parse the Salient Statistics table from commodity page text."""
    result = {"years": [], "data": {}}
    
    # Find years header (e.g., "2020  2021  2022  2023  2024e")
    years_match = re.search(r'(?:Salient Statistics[^:]*:\s*)?(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4}e?)', text)
    if years_match:
        result["years"] = [years_match.group(i) for i in range(1, 6)]
    
    # Find the statistics section
    stats_section_match = re.search(
        r'Salient Statistics[^:]*:\s*(.*?)(?=Price:|Employment:|Net import|Recycling:|Import Sources|Tariff:|Depletion|Government Stockpile|Events,|World Mine)',
        text, re.DOTALL | re.IGNORECASE
    )
    
    if not stats_section_match:
        return result
    
    stats_text = stats_section_match.group(1)
    lines = stats_text.strip().split('\n')
    
    current_category = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if this is a category header (ends with colon)
        if line.endswith(':') and not re.match(r'^[\d,\.\(\)\-\s]+$', line):
            category = line.rstrip(':').strip()
            if category and len(category) > 2:
                current_category = category
                if current_category not in result["data"]:
                    result["data"][current_category] = {}
                continue
        
        # Try to parse as data row: label followed by numbers
        # Pattern: text followed by 5 year values (numbers with commas, parens for negative)
        data_match = re.match(
            r'^(.+?)\s{2,}([\d,\.]+(?:\s+[\d,\.\(\)e\-]+){0,4})\s*$',
            line
        )
        
        if data_match:
            label = data_match.group(1).strip()
            values_str = data_match.group(2)
            
            # Parse all numeric values from the line
            values = re.findall(r'[\d,]+\.?\d*|\(\d+(?:,\d+)*(?:\.\d+)?\)|\-\d+|\de\d+', values_str)
            
            if label and values:
                if current_category is None:
                    current_category = "General"
                    if current_category not in result["data"]:
                        result["data"][current_category] = {}
                
                result["data"][current_category][label] = values
    
    return result


def parse_world_production(text: str) -> list:
    """Parse World Mine Production and Reserves table."""
    result = []
    
    # Find the world production section
    world_match = re.search(
        r'World Mine Production and Reserves[^:]*:(.*?)(?=World Resources|Substitutes|^[A-Z][a-z]+\s*:|eEstimated|$)',
        text, re.DOTALL
    )
    
    if not world_match:
        return result
    
    world_text = world_match.group(1)
    lines = world_text.strip().split('\n')
    
    # Look for country data rows
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Pattern: Country name followed by production values and reserves
        # e.g., "United States  41,600 45,000 1,900,000"
        country_match = re.match(
            r'^([A-Z][a-zA-Z\s,]+?)\s{2,}([\d,NA\s]+)$',
            line
        )
        
        if country_match:
            country = country_match.group(1).strip()
            values_str = country_match.group(2).strip()
            
            # Parse values
            values = re.findall(r'[\d,]+|NA', values_str)
            
            if len(values) >= 2:
                entry = {
                    "country": country,
                    "production_2023": values[0] if len(values) > 0 else None,
                    "production_2024": values[1] if len(values) > 1 else None,
                    "reserves": values[2] if len(values) > 2 else None
                }
                result.append(entry)
    
    return result


def parse_prices(text: str) -> dict:
    """Parse price data from commodity page."""
    result = {}
    
    # Find price section
    price_match = re.search(
        r'Price[,\s][^:]*:(.*?)(?=Employment|Net import|Recycling|Import Sources|Tariff|Depletion|$)',
        text, re.DOTALL
    )
    
    if not price_match:
        return result
    
    price_text = price_match.group(1)
    lines = price_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Pattern: commodity/grade followed by prices
        price_line_match = re.match(
            r'^(.+?),?\s+(?:average|dollars[^,]*,)?\s*([\d,\.\s]+)$',
            line, re.IGNORECASE
        )
        
        if price_line_match:
            item = price_line_match.group(1).strip()
            values = re.findall(r'[\d,\.]+', price_line_match.group(2))
            if item and values:
                result[item] = values
    
    return result


def parse_commodity_page(text: str) -> dict:
    """Extract all structured data from a commodity page."""
    result = {
        "commodity": None,
        "prepared_by": None,
        "contact": None,
        "data_unit": None,
        "domestic_production_and_use": None,
        "salient_statistics": {},
        "world_production": [],
        "prices": {},
        "import_sources": None,
        "tariff": None,
        "recycling": None,
        "resources": None,
        "substitutes": None
    }
    
    # Extract commodity name from header
    header_match = re.search(r'Prepared by ([^\[]+)\s*\[([^\]]+)\]\s*([A-Z][A-Za-z\s\-\,]+)', text)
    if header_match:
        result["prepared_by"] = header_match.group(1).strip()
        result["contact"] = header_match.group(2).strip()
        result["commodity"] = header_match.group(3).strip()
    
    # Extract data unit
    unit_match = re.search(r'\[Data in ([^\]]+)\]', text)
    if unit_match:
        result["data_unit"] = unit_match.group(1).strip()
    
    # Extract Domestic Production and Use
    prod_match = re.search(
        r'Domestic Production and Use[^:]*:\s*(.*?)(?=Salient Statistics|Recycling:|Import Sources)',
        text, re.DOTALL
    )
    if prod_match:
        result["domestic_production_and_use"] = prod_match.group(1).strip().replace('\n', ' ')
    
    # Parse salient statistics
    result["salient_statistics"] = parse_salient_statistics(text)
    
    # Parse world production
    result["world_production"] = parse_world_production(text)
    
    # Parse prices
    result["prices"] = parse_prices(text)
    
    # Extract import sources
    import_match = re.search(
        r'Import Sources[^:]*:\s*(.*?)(?=Tariff:|Depletion|^[A-Z][a-z]+:)',
        text, re.DOTALL
    )
    if import_match:
        result["import_sources"] = import_match.group(1).strip().replace('\n', ' ')
    
    # Extract tariff information
    tariff_match = re.search(
        r'Tariff[^:]*:\s*(.*?)(?=Depletion|^[A-Z][a-z]+:|World|Substitutes|$)',
        text, re.DOTALL
    )
    if tariff_match:
        result["tariff"] = tariff_match.group(1).strip().replace('\n', ' ')
    
    # Extract recycling info
    recycle_match = re.search(
        r'Recycling[^:]*:\s*(.*?)(?=Import Sources|Tariff|^[A-Z][a-z]+:)',
        text, re.DOTALL
    )
    if recycle_match:
        result["recycling"] = recycle_match.group(1).strip().replace('\n', ' ')
    
    # Extract world resources
    resources_match = re.search(
        r'World Resources[^:]*:\s*(.*?)(?=Substitutes:|eEstimated|^[A-Z][a-z]+:|$)',
        text, re.DOTALL
    )
    if resources_match:
        result["resources"] = resources_match.group(1).strip().replace('\n', ' ')
    
    # Extract substitutes
    subst_match = re.search(
        r'Substitutes[^:]*:\s*(.*?)(?=eEstimated|NA|^\d|^[A-Z][a-z]+:|$)',
        text, re.DOTALL
    )
    if subst_match:
        result["substitutes"] = subst_match.group(1).strip().replace('\n', ' ')
    
    return result


async def get_commodity_pdf(commodity: str) -> dict:
    """Fetch and parse a specific commodity's PDF."""
    # Try direct PDF URL first
    commodity_slug = commodity.lower().replace(' ', '-').replace(',', '')
    direct_url = f"{BASE_URL}/mcs2025-{commodity_slug}.pdf"
    
    try:
        pdf_data = await fetch_pdf(direct_url)
    except aiohttp.ClientError:
        # Fall back to full MCS PDF
        return await get_from_full_pdf(commodity)
    
    reader = PdfReader(io.BytesIO(pdf_data))
    
    # Extract text from all pages
    full_text = ""
    for page in reader.pages:
        text = page.extract_text() or ""
        full_text += text + "\n"
    
    return parse_commodity_page(full_text)


async def get_from_full_pdf(commodity: str) -> dict:
    """Extract commodity data from the full MCS PDF."""
    url = f"{BASE_URL}/mcs2025.pdf"
    
    pdf_data = await fetch_pdf(url)
    reader = PdfReader(io.BytesIO(pdf_data))
    
    # Find the commodity page
    commodity_lower = commodity.lower()
    page_num = None
    
    # Check our mapping first
    for name, pg in COMMODITY_PAGES.items():
        if commodity_lower in name or name in commodity_lower:
            page_num = pg
            break
    
    if page_num is None:
        # Search through pages
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if re.search(rf'\b{re.escape(commodity_upper := commodity.upper())}\b', text, re.IGNORECASE):
                # Verify it's a commodity page (has Prepared by line)
                if 'Prepared by' in text:
                    page_num = i
                    break
    
    if page_num is None:
        return {"error": f"Commodity '{commodity}' not found in MCS 2025"}
    
    # Extract from the page(s) - some commodities span 2 pages
    full_text = ""
    for pg in range(page_num, min(page_num + 2, len(reader.pages))):
        text = reader.pages[pg].extract_text() or ""
        full_text += text + "\n"
        # Stop if we hit another commodity
        if pg > page_num and re.search(r'Prepared by.*\[.*\]\s+[A-Z]{3,}', text):
            break
    
    return parse_commodity_page(full_text)


async def list_commodities() -> dict:
    """List all available commodities in MCS 2025."""
    url = f"{BASE_URL}/mcs2025.pdf"
    
    try:
        pdf_data = await fetch_pdf(url)
        reader = PdfReader(io.BytesIO(pdf_data))
        
        commodities = []
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            
            # Look for commodity header pattern
            match = re.search(r'Prepared by [^\[]+\[[^\]]+\]\s+([A-Z][A-Za-z\s,\-&]+?)(?:\d+)?$', 
                            text.split('\n')[0] if text else '')
            if match:
                commodity = match.group(1).strip()
                commodity = re.sub(r'\d+$', '', commodity).strip()
                if 3 < len(commodity) < 50:
                    commodities.append({
                        "name": commodity,
                        "page": i + 1
                    })
        
        return {
            "total": len(commodities),
            "commodities": commodities
        }
    except Exception as e:
        return {"error": str(e)}


async def get_full_pdf_text() -> dict:
    """Fetch and extract text from the full MCS PDF."""
    url = f"{BASE_URL}/mcs2025.pdf"
    
    try:
        pdf_data = await fetch_pdf(url)
        reader = PdfReader(io.BytesIO(pdf_data))
        
        return {
            "total_pages": len(reader.pages),
            "url": url,
            "size_bytes": len(pdf_data)
        }
    except Exception as e:
        return {"error": str(e)}


async def get_rare_earths() -> dict:
    """Fetch and parse the Rare Earths commodity PDF with detailed table extraction."""
    url = f"{BASE_URL}/mcs2025-rare-earths.pdf"
    
    try:
        pdf_data = await fetch_pdf(url)
        reader = PdfReader(io.BytesIO(pdf_data))
        
        result = {
            "commodity": "Rare Earths",
            "url": url,
            "pages": []
        }
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            page_data = {
                "page_number": i + 1,
                "text": text,
                "tables": {}
            }
            
            # Parse structured data
            if i == 0:
                page_data["tables"]["salient_statistics"] = parse_salient_statistics(text)
                page_data["tables"]["prices"] = parse_prices(text)
            elif i == 1:
                page_data["tables"]["world_production"] = parse_world_production(text)
            
            result["pages"].append(page_data)
        
        # Add parsed commodity data
        full_text = "\n".join(p["text"] for p in result["pages"])
        result["parsed"] = parse_commodity_page(full_text)
        
        return result
    except Exception as e:
        return {"error": str(e)}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for USGS MCS PDF extraction.
    
    Functions:
    - get_commodity: Extract data for a specific mineral commodity
    - list_commodities: List all available commodities in MCS 2025
    - get_rare_earths: Detailed extraction of Rare Earths data
    - get_full_info: Get information about the full MCS PDF
    """
    function = params.get("function", "list_commodities")
    
    try:
        if function == "get_commodity":
            commodity = params.get("commodity")
            if not commodity:
                return {"error": "Missing required parameter: commodity"}
            return await get_commodity_pdf(commodity)
        
        elif function == "list_commodities":
            return await list_commodities()
        
        elif function == "get_rare_earths":
            return await get_rare_earths()
        
        elif function == "get_full_info":
            return await get_full_pdf_text()
        
        else:
            return {"error": f"Unknown function: {function}"}
    
    except aiohttp.ClientError as e:
        return {"error": f"HTTP error: {str(e)}"}
    except Exception as e:
        return {"error": f"Processing error: {str(e)}"}