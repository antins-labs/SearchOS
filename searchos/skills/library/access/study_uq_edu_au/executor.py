"""
UQ Study Portal Access Skill

Extracts program information from University of Queensland's study portal.
Supports program search via JSON:API and detailed data extraction from HTML pages.
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin, quote
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://study.uq.edu.au"
JSONAPI_URL = f"{BASE_URL}/jsonapi/uq_program/uq_program"


async def search_programs(
    session: aiohttp.ClientSession,
    title: Optional[str] = None,
    program_code: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search programs via JSON:API"""
    
    params = {"page[limit]": str(limit)}
    
    # Build filters
    if program_code:
        params["filter[code][value]"] = program_code
    
    if title:
        params["filter[title][condition][path]"] = "title"
        params["filter[title][condition][operator]"] = "CONTAINS"
        params["filter[title][condition][value]"] = title
    
    if year:
        params["filter[year][value]"] = str(year)
    
    try:
        async with session.get(
            JSONAPI_URL,
            params=params,
            headers={"Accept": "application/vnd.api+json"}
        ) as resp:
            if resp.status != 200:
                return {
                    "error": f"API request failed with status {resp.status}",
                    "programs": []
                }
            
            data = await resp.json()
            programs = []
            
            for prog in data.get("data", []):
                attrs = prog.get("attributes", {})
                programs.append({
                    "id": prog.get("id"),
                    "code": attrs.get("code"),
                    "title": attrs.get("title"),
                    "year": attrs.get("year"),
                })
            
            return {
                "programs": programs,
                "count": len(programs),
                "has_more": "next" in data.get("links", {})
            }
    
    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "programs": []
        }


def build_slug(title: str) -> str:
    """Build URL slug from program title.
    
    UQ uses a specific slug format:
    - Lowercase
    - Remove "of" 
    - Remove parentheses and special chars
    - Replace spaces with hyphens
    """
    slug = title.lower()
    # Remove "of" word (UQ convention)
    slug = re.sub(r'\bof\b', '', slug)
    # Remove content in parentheses and special chars
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    # Normalize whitespace
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


async def get_program_detail(
    session: aiohttp.ClientSession,
    program_code: str,
    year: Optional[int] = None,
) -> dict[str, Any]:
    """Get detailed program information by scraping the program page"""
    
    # First get basic info from API
    search_params = {"filter[code][value]": program_code, "page[limit]": "10"}
    
    try:
        async with session.get(
            JSONAPI_URL,
            params=search_params,
            headers={"Accept": "application/vnd.api+json"}
        ) as resp:
            api_data = await resp.json()
            programs = api_data.get("data", [])
    except Exception as e:
        return {
            "error": f"Failed to fetch program from API: {str(e)}",
            "program_code": program_code
        }
    
    if not programs:
        return {
            "error": f"Program with code {program_code} not found",
            "program_code": program_code
        }
    
    # Filter by year if specified
    if year:
        programs = [p for p in programs if p.get("attributes", {}).get("year") == year]
        if not programs:
            return {
                "error": f"Program {program_code} not found for year {year}",
                "program_code": program_code
            }
    
    # Use first matching program
    program = programs[0]
    attrs = program.get("attributes", {})
    
    # Build the URL slug
    title = attrs.get("title", "")
    slug = build_slug(title)
    
    # Build program URL
    program_url = f"{BASE_URL}/study-options/programs/{slug}-{program_code}"
    
    try:
        async with session.get(program_url) as resp:
            if resp.status == 404:
                # Try alternate slug format (with "of" word)
                slug_alt = title.lower()
                slug_alt = re.sub(r'[^a-z0-9\s-]', '', slug_alt)
                slug_alt = re.sub(r'\s+', '-', slug_alt)
                slug_alt = re.sub(r'-+', '-', slug_alt).strip('-')
                alt_url = f"{BASE_URL}/study-options/programs/{slug_alt}-{program_code}"
                
                async with session.get(alt_url) as resp2:
                    if resp2.status == 200:
                        html = await resp2.text()
                        program_url = alt_url
                    else:
                        return {
                            "error": f"Program page not found (status {resp.status})",
                            "program_code": program_code,
                            "attempted_urls": [program_url, alt_url]
                        }
            elif resp.status != 200:
                return {
                    "error": f"Failed to fetch program page (status {resp.status})",
                    "program_code": program_code
                }
            else:
                html = await resp.text()
    except Exception as e:
        return {
            "error": f"Request failed: {str(e)}",
            "program_code": program_code
        }
    
    # Parse HTML
    return parse_program_page(html, program_url, attrs)


def parse_program_page(html: str, url: str, basic_info: dict) -> dict[str, Any]:
    """Parse program details from HTML page"""
    
    soup = BeautifulSoup(html, 'html.parser')
    body_text = soup.get_text(separator='\n', strip=True)
    
    result = {
        "url": url,
        "program_code": basic_info.get("code"),
        "title": basic_info.get("title"),
        "year": basic_info.get("year"),
    }
    
    # Extract from meta tags
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content')
    
    meta_type = soup.find('meta', attrs={'name': 'uq:program_type'})
    if meta_type:
        result["program_type"] = meta_type.get('content')
    
    # Extract title from h1
    h1 = soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Extract key info using regex patterns
    patterns = {
        "campus": r"Location\s+(St Lucia|Gatton|Herston|Digital|Online)",
        "duration": r"Duration\s+(\d+\s*(?:Years?|Months?|Semesters?)(?:\s*\([^)]+\))?)",
        "annual_fee": r"Fees?\s+A?\$([\d,]+)",
        "cricos_code": r"CRICOS(?:\s+Code)?\s+([A-Z0-9]+)",
        "aqf_level": r"AQF\s+Level\s+(\d+)",
        "start_semesters": r"Start Semester\s+([^\n]+?)(?:\s*Program|\s*CRICOS|\s*AQF|\n|$)",
    }
    
    for key, pattern in patterns.items():
        if key == "aqf_level":
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result[key] = int(match.group(1))
        elif key == "annual_fee":
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result[key] = match.group(1).replace(',', '')
        else:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                result[key] = match.group(1).strip()
    
    # Extract location from meta tag as fallback
    if "campus" not in result:
        locality = soup.find('meta', attrs={'property': 'og:locality'})
        if locality:
            result["campus"] = locality.get('content')
    
    # Extract highlights (bullet points after "Program highlights" heading)
    result["highlights"] = extract_list_items(soup, "Program highlights")
    
    # Extract what you'll learn
    result["learning_methods"] = extract_list_items(soup, "How you'll learn")
    
    # Extract sample courses
    result["sample_courses"] = extract_list_items(soup, "What you'll study")
    
    # Extract careers
    result["careers"] = extract_list_items(soup, "Career possibilities")
    
    # Extract accreditation
    result["accreditation"] = extract_list_items(soup, "Program accreditation")
    
    # Extract professional memberships
    result["professional_memberships"] = extract_list_items(soup, "Professional memberships")
    
    # Extract overview section
    overview = extract_section_text(soup, "Overview")
    if overview:
        # Clean up the overview text
        overview = re.sub(r'\s+', ' ', overview)
        overview = re.sub(r'\s*(Domestic|International|Begin study|Select|Scholarships|See full entry).*$', '', overview, flags=re.IGNORECASE)
        result["overview"] = overview.strip()
    
    # Extract entry requirements section
    entry_req = extract_section_text(soup, "Entry requirements")
    if entry_req:
        # Clean up and truncate
        entry_req = re.sub(r'\s+', ' ', entry_req)
        result["entry_requirements"] = entry_req[:2000].strip()
    
    # Extract course links
    result["course_links"] = []
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if '/course/' in href or '/subject/' in href:
            result["course_links"].append({
                "name": a.get_text(strip=True),
                "url": urljoin(BASE_URL, href)
            })
    
    return result


def extract_list_items(soup: BeautifulSoup, heading_text: str) -> list[str]:
    """Extract list items following a heading"""
    items = []
    
    for heading in soup.find_all(['h2', 'h3']):
        if heading_text.lower() in heading.get_text().lower():
            # Look at next siblings
            sibling = heading.find_next_sibling()
            count = 0
            while sibling and count < 10:
                if sibling.name in ['h2', 'h3']:
                    break
                if sibling.name in ['ul', 'ol']:
                    for li in sibling.find_all('li'):
                        text = li.get_text(strip=True)
                        if text and len(text) > 10:
                            # Clean up text
                            text = re.sub(r'\s+', ' ', text)
                            items.append(text)
                sibling = sibling.find_next_sibling()
                count += 1
            break
    
    return items


def extract_section_text(soup: BeautifulSoup, heading_text: str) -> Optional[str]:
    """Extract text from a section following a heading"""
    
    for heading in soup.find_all(['h2', 'h3']):
        if heading_text.lower() in heading.get_text().lower():
            parts = []
            sibling = heading.find_next_sibling()
            count = 0
            while sibling and count < 20:
                if sibling.name in ['h2', 'h3']:
                    break
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        parts.append(text)
                sibling = sibling.find_next_sibling()
                count += 1
            return ' '.join(parts) if parts else None
    
    return None


async def list_all_programs(
    session: aiohttp.ClientSession,
    limit: int = 100,
) -> dict[str, Any]:
    """List all available programs"""
    
    all_programs = []
    offset = 0
    page_size = 100
    
    try:
        while True:
            params = {
                "page[limit]": str(page_size),
                "page[offset]": str(offset),
                "sort": "title"
            }
            
            async with session.get(
                JSONAPI_URL,
                params=params,
                headers={"Accept": "application/vnd.api+json"}
            ) as resp:
                if resp.status != 200:
                    return {
                        "error": f"API request failed with status {resp.status}",
                        "programs": all_programs
                    }
                
                data = await resp.json()
                programs = data.get("data", [])
                
                for prog in programs:
                    attrs = prog.get("attributes", {})
                    all_programs.append({
                        "id": prog.get("id"),
                        "code": attrs.get("code"),
                        "title": attrs.get("title"),
                        "year": attrs.get("year"),
                    })
                
                # Check if there are more pages
                if len(programs) < page_size or "next" not in data.get("links", {}):
                    break
                
                offset += page_size
                
                # Stop if we've reached the limit
                if limit and len(all_programs) >= limit:
                    all_programs = all_programs[:limit]
                    break
        
        return {
            "programs": all_programs,
            "count": len(all_programs)
        }
    
    except Exception as e:
        return {
            "error": f"Failed to list programs: {str(e)}",
            "programs": all_programs
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the UQ Study skill.
    
    Supported functions:
    - get_program: Get detailed information about a specific program
    - search_programs: Search for programs by title or code
    - list_programs: List all available programs
    
    Parameters:
    - function: The function to call (required)
    - program_code: Program code for get_program (e.g., "5743")
    - title: Title search term for search_programs
    - year: Filter by year (optional)
    - limit: Maximum number of results (optional)
    """
    
    function = params.get("function", "")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "available_functions": ["get_program", "search_programs", "list_programs"]
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "get_program":
            program_code = params.get("program_code")
            if not program_code:
                return {
                    "error": "Missing required parameter: program_code",
                    "function": function
                }
            
            year = params.get("year")
            return await get_program_detail(session, program_code, year)
        
        elif function == "search_programs":
            title = params.get("title")
            program_code = params.get("program_code")
            year = params.get("year")
            limit = params.get("limit", 50)
            
            return await search_programs(
                session,
                title=title,
                program_code=program_code,
                year=year,
                limit=limit
            )
        
        elif function == "list_programs":
            limit = params.get("limit", 100)
            return await list_all_programs(session, limit=limit)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": ["get_program", "search_programs", "list_programs"]
            }


# For testing
if __name__ == "__main__":
    import sys
    import json
    
    async def test():
        # Test get_program
        print("=== Testing get_program ===")
        result = await execute({"function": "get_program", "program_code": "5743"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n=== Testing search_programs ===")
        result = await execute({"function": "search_programs", "title": "engineering", "limit": 5})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())