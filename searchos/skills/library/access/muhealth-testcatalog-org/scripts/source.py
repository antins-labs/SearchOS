"""
MU Health Care Laboratory Test Catalog - CBC Reference Ranges Extractor

Extracts structured medical reference tables (lab test ranges) from 
muhealth.testcatalog.org, specifically CBC (Complete Blood Count) reference ranges.
"""

import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the MU Health test catalog skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_test_reference_ranges' or 'search_test')
            - test_code: Optional test code (e.g., 'CBCREF')
            - test_name: Optional test name to search for

    
    Returns:
        Dictionary with structured reference range data
    """
    function = params.get("function", "get_test_reference_ranges")
    
    if function == "get_test_reference_ranges":
        return await get_test_reference_ranges(params)
    elif function == "search_test":
        return await search_test(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def get_test_reference_ranges(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch and parse reference ranges for a specific test code.
    
    Args:
        params: Dictionary with 'test_code' (default: 'CBCREF')

    
    Returns:
        Structured dictionary with test name, code, and reference ranges by analyte
    """
    from playwright.async_api import async_playwright
    
    test_code = params.get("test_code", "CBCREF").upper()
    
    # Validate test code format
    if not re.match(r'^[A-Z0-9]+$', test_code):
        return {
            "error": "Invalid test code format. Use alphanumeric codes only.",
            "success": False
        }
    
    url = f"https://muhealth.testcatalog.org/show/{test_code}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Cache-Control': 'max-age=0',
                        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'document',
                        'sec-fetch-mode': 'navigate',
                        'sec-fetch-site': 'none',
                        'sec-fetch-user': '?1',
                        'upgrade-insecure-requests': '1'
                    }
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                
                # Check for access denied
                title = await page.title()
                if "Access Denied" in title:
                    return {
                        "error": "Access denied by the server. The site may be blocking requests.",
                        "success": False,
                        "url": url
                    }
                
                # Get page content
                body_text = await page.evaluate('() => document.body.innerText')
                
                # Extract test name and description
                test_name = extract_test_name(body_text, test_code)
                
                # Parse reference ranges
                reference_ranges = parse_reference_ranges(body_text)
                
                return {
                    "success": True,
                    "test_code": test_code,
                    "test_name": test_name,
                    "url": url,
                    "reference_ranges": reference_ranges,
                    "raw_text_length": len(body_text)
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "error": f"Failed to fetch test reference ranges: {str(e)}",
            "success": False,
            "url": url
        }


async def search_test(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for a test by name in the catalog.
    Note: This is a basic implementation that tries common test codes.
    
    Args:
        params: Dictionary with 'test_name' or 'test_code'

    
    Returns:
        Dictionary with search results
    """
    test_name = params.get("test_name", "").upper()
    test_code = params.get("test_code", "").upper()
    
    if not test_name and not test_code:
        return {
            "error": "Please provide either test_name or test_code",
            "success": False
        }
    
    # Common test code mappings
    common_tests = {
        "CBC": "CBCREF",
        "CBC REFERENCE": "CBCREF",
        "COMPLETE BLOOD COUNT": "CBCREF",
        "CBCREF": "CBCREF",
        "CMP": "CMP",
        "BMP": "BMP",
        "LIPID": "LIPID",
        "TSH": "TSH",
        "METABOLIC": "METABOLIC",
        "HEMOGLOBIN": "CBCREF",
        "HEMATOCRIT": "CBCREF",
        "WBC": "CBCREF",
        "RBC": "CBCREF",
        "PLATELET": "CBCREF"
    }
    
    # Try to find matching test code
    found_code = None
    if test_code:
        found_code = test_code
    else:
        for name, code in common_tests.items():
            if name in test_name or test_name in name:
                found_code = code
                break
    
    if not found_code:
        return {
            "error": f"Could not find test matching '{test_name}'. Try using a specific test code.",
            "success": False,
            "suggestion": "Common test codes include: CBCREF (CBC Reference Ranges), CMP, BMP, TSH, etc."
        }
    
    # Fetch the reference ranges
    return await get_test_reference_ranges({"test_code": found_code})


def extract_test_name(text: str, test_code: str) -> str:
    """Extract the test name from page text."""
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if f"Test Code {test_code}" in line:
            # Next line is usually the test name
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return f"Test {test_code}"


def parse_reference_ranges(text: str) -> dict[str, Any]:
    """
    Parse reference ranges from the page text.
    
    Returns a structured dictionary with analytes and their reference ranges.
    """
    ranges = {}
    
    # Clean up text - remove excessive whitespace and navigation elements
    # Find the main content section (after "Reference or Target Ranges")
    main_content = text
    if "Reference or Target Ranges" in text:
        parts = text.split("Reference or Target Ranges")
        if len(parts) > 1:
            main_content = parts[1]
    
    # Split into lines for processing
    lines = main_content.strip().split('\n')
    
    # Define analyte markers - these are the section headers
    # Order matters - they appear in this order in the table
    analyte_markers = [
        ("RBC", "RED BLOOD CELL COUNT"),
        ("Hemoglobin", "HEMOGLOBIN"),
        ("Hematocrit", "HEMATOCRIT"),
        ("MCV", "MEAN CORPUSCULAR VOLUME"),
        ("RDW-SD", "RDW-SD"),
        ("RDW", "RED CELL DISTRIBUTION WIDTH"),
        ("WBC", "WHITE BLOOD CELL COUNT"),
        ("MCHC", "MCHC:"),
        ("MCH", "MCH:"),
        ("Lymphocytes", "LYMPHOCYTES"),
        ("Neutrophils", "NEUTROPHILS"),
        ("Eosinophils", "EOSINOPHILS"),
        ("Monocytes", "MONOCYTES"),
        ("Immature Granulocytes", "IMMATURE GRANULOCYTES"),
        ("Basophils", "BASOPHILS"),
        ("Platelets", "PLATELETS"),
        ("MPV", "MPV:"),
        ("IPF", "IPF:"),
        ("Reticulocyte Percent", "Retic %"),
        ("Reticulocyte Count", "Retic #"),
    ]
    
    # Find positions of each analyte marker
    analyte_positions = []
    for short_name, full_marker in analyte_markers:
        for i, line in enumerate(lines):
            if full_marker.upper() in line.upper():
                analyte_positions.append((i, short_name, full_marker))
                break
    
    # Sort by position
    analyte_positions.sort(key=lambda x: x[0])
    
    # Extract sections
    for idx, (pos, short_name, marker) in enumerate(analyte_positions):
        # Find end position (start of next analyte or end of text)
        if idx + 1 < len(analyte_positions):
            end_pos = analyte_positions[idx + 1][0]
        else:
            end_pos = len(lines)
        
        section_lines = lines[pos:end_pos]
        section_text = '\n'.join(section_lines)
        
        ranges[short_name] = parse_analyte_section(section_text, short_name)
    
    return ranges


def parse_analyte_section(section: str, analyte_name: str) -> dict[str, Any]:
    """
    Parse a single analyte section into structured data.
    
    Returns:
        Dictionary with 'ranges' list containing age/sex-specific reference ranges
    """
    result = {
        "analyte": analyte_name,
        "ranges": []
    }
    
    lines = section.strip().split('\n')
    
    current_sex = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Skip header lines that are just the analyte name
        if analyte_name.upper() in line.upper() and len(line) < 60:
            # Check if it's a simple header (not containing range data)
            if not re.search(r'[0-9]+\s*[-–]\s*[0-9]+', line):
                continue
        
        # Detect sex headers
        if line.lower() in ['males', 'male']:
            current_sex = 'Male'
            continue
        elif line.lower() in ['females', 'female']:
            current_sex = 'Female'
            continue
        
        # Parse reference range lines
        # Patterns like: "Birth: 3.90-5.50×10(12)/L" or "Adults: 13.5-17.5 g/dL"
        # or "2 years: 11.0-14.0 g/dL" or "12-15 years: 12.8-16.0 g/dL"
        
        # Match age: value pattern
        range_match = re.match(
            r'^([A-Za-z0-9\-\s,<>]+?):\s*([0-9.,\-×x\(\)\/%\s]+(?:g\/dL|fL|pg|×10\([0-9]+\)/L|×10\^[0-9]+/L|/L|%|[0-9])).*$',
            line
        )
        
        if range_match:
            age_group = range_match.group(1).strip()
            value = range_match.group(2).strip()
            
            # Skip if this looks like another analyte header
            skip_keywords = ['RED BLOOD', 'HEMOGLOBIN', 'HEMATOCRIT', 'WHITE BLOOD', 
                           'MEAN CORPUSCULAR', 'PLATELET', 'LYMPHOCYTE', 'NEUTROPHIL', 
                           'EOSINOPHIL', 'MONOCYTE', 'BASOPHIL', 'RDW', 'MCH', 'MCHC',
                           'MCV', 'WBC', 'RBC', 'MPV', 'IPF', 'RETIC']
            if any(skip in age_group.upper() for skip in skip_keywords):
                continue
            
            # Clean up the value
            value = re.sub(r'\s+', ' ', value)  # Normalize whitespace
            
            # Validate this looks like a reference range (contains numbers and a separator)
            if re.search(r'[0-9]', value) and ('-' in value or '–' in value or 'to' in value.lower()):
                range_entry = {
                    "age_group": age_group,
                    "reference_range": value
                }
                
                if current_sex:
                    range_entry["sex"] = current_sex
                
                result["ranges"].append(range_entry)
    
    # For simple formats (like MCH, MCHC, MPV, IPF) without explicit age groups
    if not result["ranges"]:
        # Try simpler pattern for single-value entries
        simple_match = re.search(r'([0-9]+(?:\.[0-9]+)?\s*[-–]\s*[0-9]+(?:\.[0-9]+)?\s*(?:g\/dL|fL|pg|%|[0-9]))', section)
        if simple_match:
            result["ranges"].append({
                "age_group": "All ages",
                "reference_range": simple_match.group(1).strip()
            })
    
    # Handle special table format for Immature Granulocytes
    if analyte_name == "Immature Granulocytes" and not result["ranges"]:
        result = parse_ig_table(section)
    
    # Handle special format for Reticulocytes
    if analyte_name in ["Reticulocyte Percent", "Reticulocyte Count"] and not result["ranges"]:
        result = parse_retic_table(section, analyte_name)
    
    return result


def parse_ig_table(section: str) -> dict[str, Any]:
    """Parse the Immature Granulocytes table format."""
    result = {
        "analyte": "Immature Granulocytes",
        "ranges": []
    }
    
    # Pattern: Age group followed by percentage and absolute count
    # Example: "Neonate 0 hrs - 48 hrs  0.0-6.2  0.00-1.46"
    lines = section.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or 'IMMATURE' in line.upper():
            continue
        
        # Try to match the table row format
        match = re.match(r'(.+?)\s+([0-9.,\-]+)\s+([0-9.,\-]+)', line)
        if match:
            age_group = match.group(1).strip()
            percent = match.group(2).strip()
            absolute = match.group(3).strip()
            
            result["ranges"].append({
                "age_group": age_group,
                "reference_range": f"{percent}% (IG 10^9/L: {absolute})"
            })
    
    return result


def parse_retic_table(section: str, analyte_name: str) -> dict[str, Any]:
    """Parse Reticulocyte table format with Male/Female sections."""
    result = {
        "analyte": analyte_name,
        "ranges": []
    }
    
    lines = section.strip().split('\n')
    current_sex = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line.lower() in ['male:', 'male']:
            current_sex = 'Male'
            continue
        elif line.lower() in ['female:', 'female']:
            current_sex = 'Female'
            continue
        
        # Match age: range pattern
        match = re.match(r'(.+?):\s*([0-9.,\-\s]+)', line)
        if match:
            age_group = match.group(1).strip()
            value = match.group(2).strip()
            
            range_entry = {
                "age_group": age_group,
                "reference_range": value
            }
            
            if current_sex:
                range_entry["sex"] = current_sex
            
            result["ranges"].append(range_entry)
    
    return result


def format_reference_ranges(ranges: dict[str, Any]) -> str:
    """Format reference ranges as a human-readable string."""
    output_lines = []
    
    for analyte, data in ranges.items():
        if isinstance(data, dict) and data.get("ranges"):
            output_lines.append(f"\n{analyte}:")
            current_sex = None
            for r in data["ranges"]:
                sex = r.get("sex", "")
                age = r.get("age_group", "")
                value = r.get("reference_range", "")
                
                if sex and sex != current_sex:
                    output_lines.append(f"  {sex}:")
                    current_sex = sex
                
                indent = "    " if sex else "  "
                output_lines.append(f"{indent}{age}: {value}")
    
    return "\n".join(output_lines)