"""
Harvard GSAS Programs Access Skill

Provides access to graduate programs from the Harvard Kenneth C. Griffin Graduate School of Arts and Sciences.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import urllib.parse
import re

BASE_URL = "https://gsas.harvard.edu"

# Filter ID mappings discovered from the website
DEGREE_FILTERS = {
    "Doctor of Philosophy (PhD)": "157",
    "PhD": "157",
    "Master of Arts (AM)": "158",
    "AM": "158",
    "Master of Science (SM)": "159", 
    "SM": "159",
    "Master of Engineering (ME)": "160",
    "ME": "160",
    "AB/AM, AB/SM": "352",
}

AREA_FILTERS = {
    "Arts & Architecture": "168",
    "Biological Sciences": "177",
    "Engineering & Applied Sciences": "173",
    "Harvard Integrated Life Sciences": "174",
    "History": "170",
    "Humanities": "171",
    "Languages": "172",
    "Mathematics": "175",
    "Medical Sciences": "178",
    "Physical Sciences": "179",
    "Social Sciences": "50",
}

GRE_FILTERS = {
    "Required": "161",
    "Optional": "162",
    "Not Accepted": "163",
}

PROGRAM_TYPE_FILTERS = {
    "Degree Granting": "166",
    "Combined Degree": "351",
    "Summer Programs": "165",
    "Visiting Students": "164",
}


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        return await response.text()


def parse_program_list(html: str) -> list[dict]:
    """Parse program listings from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    programs = []
    
    articles = soup.select("article.node-type-program")
    
    for article in articles:
        # Get title
        title_el = article.select_one("h3, h2")
        title = title_el.get_text(strip=True) if title_el else None
        
        # Get program URL
        link_el = article.select_one("a[href*='/program/']")
        url = link_el["href"] if link_el else None
        if url and not url.startswith("http"):
            url = BASE_URL + url
        
        # Get text content for parsing
        all_text = article.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        
        # Parse GRE requirement
        gre_idx = next((i for i, l in enumerate(lines) if "GRE Requirement" in l), -1)
        gre_req = lines[gre_idx + 1] if gre_idx >= 0 and gre_idx + 1 < len(lines) else None
        
        # Parse degrees offered
        deg_idx = next((i for i, l in enumerate(lines) if "Degrees Offered" in l or "Degree Offered" in l), -1)
        degrees = []
        if deg_idx >= 0:
            # Get all degree text after the label
            for j in range(deg_idx + 1, min(deg_idx + 5, len(lines))):
                line = lines[j]
                if any(d in line for d in ["Doctor", "Master", "PhD", "AM", "SM", "ME"]):
                    degrees.append(line)
        
        # Check if it's an area of study within another program
        area_idx = next((i for i, l in enumerate(lines) if "Area of Study Within" in l), -1)
        parent_program = lines[area_idx + 1] if area_idx >= 0 and area_idx + 1 < len(lines) else None
        
        # Check for Life Sciences link
        life_sci_link = article.select_one("a[href*='life-sciences']")
        is_life_sciences = life_sci_link is not None
        
        programs.append({
            "title": title,
            "url": url,
            "gre_requirement": gre_req,
            "degrees_offered": degrees,
            "parent_program": parent_program,
            "is_life_sciences": is_life_sciences,
        })
    
    return programs


def parse_total_results(html: str) -> int:
    """Parse total number of results from the page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for "Results 1-10 displayed" or "80 Results" pattern
    text = soup.get_text(separator=" ", strip=True)
    
    # Try to find "X Results" pattern where X is the total
    match = re.search(r'(\d+)\s+Results', text)
    if match:
        return int(match.group(1))
    
    return 0


def parse_program_detail(html: str, url: str) -> dict:
    """Parse detailed program information from the program page."""
    soup = BeautifulSoup(html, "html.parser")
    
    data = {"url": url}
    
    # Title
    h1 = soup.select_one("h1, .field--name-title")
    data["title"] = h1.get_text(strip=True) if h1 else None
    
    # Header text (brief description)
    header_text = soup.select_one(".field--name-field-header-text")
    if header_text:
        data["header_text"] = header_text.get_text(strip=True)
    
    # Body/description
    body = soup.select_one(".field--name-field-body")
    if body:
        # Clean up the body text
        body_text = body.get_text(separator=" ", strip=True)
        data["body"] = body_text[:2000] + "..." if len(body_text) > 2000 else body_text
    
    # Degrees with deadlines
    degrees = []
    degree_field = soup.select_one(".field--name-field-degree")
    if degree_field:
        degree_items = degree_field.select(".field__item")
        for item in degree_items:
            deg_type = item.select_one(".field--name-field-degree-type")
            deadline = item.select_one(".field--name-field-deadline .field__item")
            apply_link = item.select_one(".field--name-field-application-link a")
            
            deg_data = {
                "type": deg_type.get_text(strip=True) if deg_type else None,
                "deadline": deadline.get_text(strip=True) if deadline else None,
                "apply_url": apply_link["href"] if apply_link else None
            }
            if deg_data["type"]:  # Only add if we have degree type
                degrees.append(deg_data)
    
    data["degrees"] = degrees if degrees else None
    
    # Contact info
    contact_name = soup.select_one(".field--name-field-contact-name")
    contact_title = soup.select_one(".field--name-field-contact-title")
    phone_field = soup.select_one(".field--name-field-phone")
    
    contact = {}
    if contact_name:
        contact["name"] = contact_name.get_text(strip=True)
    if contact_title:
        contact["title"] = contact_title.get_text(strip=True)
    if phone_field:
        # Email is often inside this field
        text = phone_field.get_text()
        email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', text)
        if email_match:
            contact["email"] = email_match.group()
    
    data["contact"] = contact if contact else None
    
    # Program website
    site_link = soup.select_one(".field--name-field-program-site-link a")
    data["program_website"] = site_link["href"] if site_link else None
    
    # GRE requirement
    gre = soup.select_one(".field--name-field-gre-requirement")
    data["gre_requirement"] = gre.get_text(strip=True) if gre else None
    
    # Areas of study
    areas = soup.select(".field--name-field-area-of-study .field__item")
    data["areas_of_study"] = [a.get_text(strip=True) for a in areas] if areas else None
    
    # Check if part of Life Sciences
    life_sci = soup.select_one(".field--name-field-hils")
    data["is_life_sciences"] = life_sci is not None
    
    return data


def parse_applying_page(html: str) -> dict:
    """Parse the applying to degree programs page."""
    soup = BeautifulSoup(html, "html.parser")
    
    sections = []
    faqs = []
    
    # Get main content area
    main = soup.select_one("article.node, main")
    if not main:
        main = soup
    
    # Find FAQ items by class
    faq_elements = main.select(".faq-question")
    for faq in faq_elements:
        question = faq.get_text(strip=True)
        # The answer is typically in the next sibling element
        answer_parts = []
        for sibling in faq.find_next_siblings():
            if sibling.name in ["h2", "h3", "h4"] and "faq-question" not in sibling.get("class", []):
                break
            text = sibling.get_text(strip=True)
            if text and len(text) > 5:
                answer_parts.append(text)
        
        if question.endswith("?") or "FAQ" in question or len(question) > 10:
            faqs.append({
                "question": question,
                "answer": " ".join(answer_parts)[:1500] if answer_parts else None
            })
    
    # Find regular content sections (h2 and h3 that aren't FAQs)
    skip_classes = ['menu', 'nav', 'footer', 'social', 'utility', 'faq-question']
    skip_texts = ['main menu', 'footer', 'utility menu', 'share', 'social']
    
    for heading in main.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True)
        classes = heading.get("class", [])
        
        # Skip navigation/menu items and FAQs
        if any(skip in " ".join(classes).lower() for skip in skip_classes):
            continue
        if any(skip in text.lower() for skip in skip_texts):
            continue
        if "faq-question" in classes:
            continue
        
        # Skip FAQ questions
        if heading.get("class") and "faq-question" in heading.get("class"):
            continue
        
        # Get content after heading
        content_parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3", "h4"]:
                break
            if sibling.name == "p":
                p_text = sibling.get_text(strip=True)
                if p_text:
                    content_parts.append(p_text)
        
        if content_parts:
            sections.append({
                "heading": text,
                "content": " ".join(content_parts)[:2000]
            })
    
    return {
        "sections": sections[:15],
        "faqs": faqs[:15]
    }


async def list_programs(
    session: aiohttp.ClientSession,
    page: int = 0,
    degrees_offered: Optional[str] = None,
    areas_of_study: Optional[str] = None,
    gre_requirement: Optional[str] = None,
    program_type: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    """List programs with optional filtering."""
    
    # Build URL with filters
    params = []
    
    filter_idx = 0
    def add_filter(filter_type: str, value: str):
        nonlocal filter_idx
        params.append(f"f[{filter_idx}]={filter_type}%3A{value}")
        filter_idx += 1
    
    if degrees_offered:
        filter_id = DEGREE_FILTERS.get(degrees_offered) or DEGREE_FILTERS.get(degrees_offered.strip())
        if filter_id:
            add_filter("degrees_offered", filter_id)
    
    if areas_of_study:
        filter_id = AREA_FILTERS.get(areas_of_study)
        if filter_id:
            add_filter("areas_of_study", filter_id)
    
    if gre_requirement:
        filter_id = GRE_FILTERS.get(gre_requirement)
        if filter_id:
            add_filter("gre_requirement", filter_id)
    
    if program_type:
        filter_id = PROGRAM_TYPE_FILTERS.get(program_type)
        if filter_id:
            add_filter("program_type", filter_id)
    
    # Add pagination
    params.append(f"page={page}")
    
    # Add search
    if search:
        params.append(f"search_api_fulltext={urllib.parse.quote(search)}")
    
    url = f"{BASE_URL}/programs?{'&'.join(params)}" if params else f"{BASE_URL}/programs"
    
    try:
        html = await fetch_html(session, url)
        programs = parse_program_list(html)
        total = parse_total_results(html)
        
        return {
            "success": True,
            "results": programs,
            "total": total,
            "page": page,
            "per_page": 10,
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


async def get_program(
    session: aiohttp.ClientSession,
    program_url: str,
) -> dict:
    """Get detailed information about a specific program."""
    
    # Build full URL if needed
    if program_url.startswith("http"):
        url = program_url
    else:
        # Ensure proper slug format
        slug = program_url.strip("/")
        url = f"{BASE_URL}/program/{slug}"
    
    try:
        html = await fetch_html(session, url)
        
        # Check if it's a 404
        if "Page not found" in html or "404" in html[:5000]:
            return {
                "success": False,
                "error": "Program not found",
                "url": url,
            }
        
        data = parse_program_detail(html, url)
        data["success"] = True
        return data
        
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Failed to fetch program: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse program: {str(e)}",
            "url": url,
        }


async def get_applying_info(
    session: aiohttp.ClientSession,
) -> dict:
    """Get information about the application process."""
    
    url = f"{BASE_URL}/apply/applying-degree-programs"
    
    try:
        html = await fetch_html(session, url)
        data = parse_applying_page(html)
        data["success"] = True
        data["url"] = url
        return data
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the GSAS Harvard access skill.
    
    Args:
        params: Dictionary containing:
            - function: One of "list_programs", "get_program", "get_applying_info"
            - Additional parameters specific to each function
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with success status and data or error message
    """
    
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "available_functions": ["list_programs", "get_program", "get_applying_info"],
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "list_programs":
            return await list_programs(
                session,
                page=params.get("page", 0),
                degrees_offered=params.get("degrees_offered"),
                areas_of_study=params.get("areas_of_study"),
                gre_requirement=params.get("gre_requirement"),
                program_type=params.get("program_type"),
                search=params.get("search"),
            )
        
        elif function == "get_program":
            program_url = params.get("program_url")
            if not program_url:
                return {
                    "success": False,
                    "error": "Missing required parameter: program_url",
                }
            return await get_program(session, program_url)
        
        elif function == "get_applying_info":
            return await get_applying_info(session)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": ["list_programs", "get_program", "get_applying_info"],
            }