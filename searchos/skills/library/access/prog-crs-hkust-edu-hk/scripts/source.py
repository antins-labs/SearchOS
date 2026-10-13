"""
HKUST Postgraduate Program Catalog Scraper

This skill scrapes structured academic program data from HKUST's Program & Course Catalog.
It extracts comprehensive program information including requirements, fees, deadlines,
curriculum, and course details.
"""

import re
from typing import Any
from bs4 import BeautifulSoup
import aiohttp


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute the HKUST program catalog scraper.
    
    Args:
        params: Dictionary containing:
            - function: "get_program" (required)
            - url: Program URL (optional, alternative to program_code and year)
            - program_code: Program code like "msc-fofb", "msc-mark" (optional if url provided)
            - academic_year: Academic year like "2026-27" (optional, defaults to current year)
            - sections: List of sections to extract (optional, defaults to all)
              Options: ["general_info", "introduction", "learning_outcomes", "curriculum", 
                        "admission_requirements", "application"]
            - include_courses: Include course details (default: True)
            - include_deadlines: Include application deadlines (default: True)
        
    Returns:
        Dictionary with program data or error information
    """
    function = params.get("function")
    
    if function == "get_program":
        return await get_program(params, ctx)
    elif function == "list_programs":
        return await list_programs(params, ctx)
    elif function == "search_courses":
        return await search_courses(params, ctx)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_program, list_programs, search_courses"
        }


async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict) -> tuple[int, str]:
    """Fetch a page and return status and HTML"""
    async with session.get(url, headers=headers, timeout=30) as response:
        html = await response.text()
        return response.status, html


async def fetch_course_details(session: aiohttp.ClientSession, base_url: str, 
                                course_data: dict, headers: dict) -> dict:
    """Fetch detailed course information via AJAX endpoint"""
    ajax_url = "https://prog-crs.hkust.edu.hk/program/ajax/courseInfo.php"
    params = {
        "is_preview": "",
        "crse_prefix": course_data.get("prefix", ""),
        "crse_log_num": course_data.get("log_num", ""),
        "crse_code": course_data.get("code", ""),
        "acad_year": course_data.get("acad_year", ""),
        "idx": course_data.get("idx", "")
    }
    
    try:
        async with session.get(ajax_url, params=params, headers=headers, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract course details from AJAX response
                name_elem = soup.find('div', class_='block-code-name')
                credit_elem = soup.find('div', class_='block-code-credit')
                desc_elem = soup.find('div', class_='course-data')
                
                return {
                    "name": name_elem.get_text(strip=True) if name_elem else None,
                    "credits": credit_elem.get_text(strip=True) if credit_elem else None,
                    "description": desc_elem.get_text(strip=True) if desc_elem else None
                }
    except Exception:
        pass
    
    return {}


async def get_program(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Extract detailed information for a specific HKUST postgraduate program.
    """
    # Get URL or construct from program_code and year
    url = params.get("url")
    
    if not url:
        program_code = params.get("program_code")
        if not program_code:
            return {
                "success": False,
                "error": "Either 'url' or 'program_code' is required"
            }
        
        academic_year = params.get("academic_year", "2026-27")
        url = f"https://prog-crs.hkust.edu.hk/pgprog/{academic_year}/{program_code}/"
    
    # Validate URL
    if "prog-crs.hkust.edu.hk/pgprog" not in url:
        return {
            "success": False,
            "error": "Invalid URL. Must be a HKUST program catalog URL."
        }
    
    # Extract parameters
    sections_filter = params.get("sections")
    include_courses = params.get("include_courses", True)
    include_deadlines = params.get("include_deadlines", True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            status, html = await fetch_page(session, url, headers)
            
            if status != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch program page: HTTP {status}",
                    "url": url
                }
            
            # Check for invalid program (page exists but no program content)
            soup = BeautifulSoup(html, 'html.parser')
            title_div = soup.find('div', class_='program-title')
            
            if not title_div:
                # Check for error indicators in page content
                page_text = soup.get_text().lower()
                if 'not found' in page_text or 'error' in page_text or 'does not exist' in page_text:
                    return {
                        "success": False,
                        "error": "Program not found. Please check the URL or program code.",
                        "url": url
                    }
                
                # Generic error if no program title
                return {
                    "success": False,
                    "error": "Program page not found or invalid program code.",
                    "url": url
                }
            
            # Extract all sections with course fetching if needed
            all_sections = await extract_all_sections_async(
                session, soup, headers, include_courses, include_deadlines
            )
    
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "url": url
        }
    
    result = {
        "success": True,
        "url": url,
        "data": {}
    }
    
    # Extract program code and year from URL
    url_match = re.search(r'/pgprog/(\d{4}-\d{2})/([^/]+)/?', url)
    if url_match:
        result["academic_year"] = url_match.group(1)
        result["program_code"] = url_match.group(2)
    
    # Extract program title
    result["data"]["title"] = title_div.get_text(strip=True) if title_div else None
    
    # Apply section filter if provided
    if sections_filter:
        section_mapping = {
            "general_info": "GENERAL INFORMATION",
            "introduction": "INTRODUCTION",
            "learning_outcomes": "LEARNING OUTCOMES",
            "curriculum": "CURRICULUM",
            "admission_requirements": "ADMISSION REQUIREMENTS",
            "application": "APPLICATION"
        }
        
        filtered_sections = {}
        for section_key in sections_filter:
            section_name = section_mapping.get(section_key.lower(), section_key.upper())
            if section_name in all_sections:
                filtered_sections[section_name] = all_sections[section_name]
        
        result["data"]["sections"] = filtered_sections
    else:
        result["data"]["sections"] = all_sections
    
    # Parse basic info into structured fields
    general_info = result["data"]["sections"].get("GENERAL INFORMATION", {})
    if isinstance(general_info, dict):
        result["data"]["parsed_info"] = parse_basic_info(general_info.get("content", ""))
    
    # Parse admission requirements
    admission = result["data"]["sections"].get("ADMISSION REQUIREMENTS", {})
    if isinstance(admission, dict):
        result["data"]["parsed_requirements"] = parse_admission_requirements(admission.get("content", ""))
    
    # Parse application info
    application = result["data"]["sections"].get("APPLICATION", {})
    if isinstance(application, dict):
        result["data"]["parsed_application"] = parse_application_info(application)
    
    return result


async def extract_all_sections_async(session: aiohttp.ClientSession, soup: BeautifulSoup, 
                                      headers: dict, include_courses: bool = True,
                                      include_deadlines: bool = True) -> dict:
    """Extract all sections from the program page with async course fetching"""
    sections = {}
    
    # Find all tab headings (section headers)
    tab_headings = soup.find_all('div', class_='block-tab-heading')
    
    for heading in tab_headings:
        section_title = heading.get_text(strip=True)
        
        # Get the content div
        content_div = heading.find_next_sibling('div', class_='block-tab-content')
        if not content_div:
            continue
        
        section_data = {
            "content": content_div.get_text('\n', strip=True)
        }
        
        # For GENERAL INFORMATION, extract structured key-value pairs
        if "GENERAL INFORMATION" in section_title.upper():
            info_dict = {}
            tab_box = soup.find('div', class_='block-tab-box')
            if tab_box:
                rows = tab_box.find_all('div', class_='block-table-row')
                for row in rows:
                    heading_cell = row.find('div', class_='block-row-heading')
                    content_cell = row.find('div', class_='block-row-content')
                    if heading_cell and content_cell:
                        key = heading_cell.get_text(strip=True)
                        value = content_cell.get_text('\n', strip=True)
                        info_dict[key] = value
            
            section_data["details"] = info_dict
        
        # For CURRICULUM, extract courses
        if "CURRICULUM" in section_title.upper() and include_courses:
            courses = []
            course_containers = content_div.find_all('div', class_='block-course-container')
            
            # Prepare course data for batch fetching
            course_fetch_data = []
            for container in course_containers:
                code_elem = container.find('div', class_='block-course-code')
                if not code_elem:
                    continue
                
                code = code_elem.get_text(strip=True)
                
                # Extract data attributes for AJAX call
                course_fetch_data.append({
                    "code": container.get('data-crse-code', ''),
                    "prefix": container.get('data-crse-prefix', ''),
                    "log_num": container.get('data-crse-log-num', ''),
                    "acad_year": container.get('data-acad-year', ''),
                    "idx": container.get('data-crse-idx', ''),
                    "display_code": code
                })
            
            # Fetch course details
            for course_info in course_fetch_data:
                course = {
                    "code": course_info["display_code"],
                    "name": None,
                    "credits": None,
                    "description": None
                }
                
                if course_info.get("code"):
                    details = await fetch_course_details(session, "", course_info, headers)
                    if details:
                        course["name"] = details.get("name")
                        course["credits"] = details.get("credits")
                        course["description"] = details.get("description")
                
                courses.append(course)
            
            section_data["courses"] = courses
            
            # Also extract credit requirements
            credit_match = re.search(r'Minimum Credit Requirement[:\s]*(\d+)', section_data["content"])
            if credit_match:
                section_data["minimum_credits"] = int(credit_match.group(1))
            
            core_match = re.search(r'Core Course[s]?[:\s]*(\d+)', section_data["content"])
            if core_match:
                section_data["core_credits"] = int(core_match.group(1))
            
            elective_match = re.search(r'Elective Course[s]?[:\s]*(\d+)', section_data["content"])
            if elective_match:
                section_data["elective_credits"] = int(elective_match.group(1))
        
        # For APPLICATION, extract deadlines and fee
        if "APPLICATION" in section_title.upper():
            if include_deadlines:
                deadlines = extract_deadlines(section_data["content"])
                if deadlines:
                    section_data["deadlines"] = deadlines
            
            # Extract application fee
            fee_match = re.search(r'Application Fee[:\s]*HK\$(\d[\d,]*)', section_data["content"])
            if fee_match:
                section_data["application_fee"] = f"HK${fee_match.group(1)}"
        
        sections[section_title] = section_data
    
    return sections


def extract_all_sections(soup: BeautifulSoup, include_courses: bool = True, include_deadlines: bool = True) -> dict:
    """Extract all sections from the program page (synchronous version for backward compatibility)"""
    sections = {}
    
    # Find all tab headings (section headers)
    tab_headings = soup.find_all('div', class_='block-tab-heading')
    
    for heading in tab_headings:
        section_title = heading.get_text(strip=True)
        
        # Get the content div
        content_div = heading.find_next_sibling('div', class_='block-tab-content')
        if not content_div:
            continue
        
        section_data = {
            "content": content_div.get_text('\n', strip=True)
        }
        
        # For GENERAL INFORMATION, extract structured key-value pairs
        if "GENERAL INFORMATION" in section_title.upper():
            info_dict = {}
            tab_box = soup.find('div', class_='block-tab-box')
            if tab_box:
                rows = tab_box.find_all('div', class_='block-table-row')
                for row in rows:
                    heading_cell = row.find('div', class_='block-row-heading')
                    content_cell = row.find('div', class_='block-row-content')
                    if heading_cell and content_cell:
                        key = heading_cell.get_text(strip=True)
                        value = content_cell.get_text('\n', strip=True)
                        info_dict[key] = value
            
            section_data["details"] = info_dict
        
        # For CURRICULUM, extract courses (basic info only - without AJAX)
        if "CURRICULUM" in section_title.upper() and include_courses:
            courses = []
            course_containers = content_div.find_all('div', class_='block-course-container')
            
            for container in course_containers:
                code_elem = container.find('div', class_='block-course-code')
                
                if code_elem:
                    course = {
                        "code": code_elem.get_text(strip=True),
                        "name": None,
                        "credits": None,
                        "description": None
                    }
                    courses.append(course)
            
            section_data["courses"] = courses
            
            # Also extract credit requirements
            credit_match = re.search(r'Minimum Credit Requirement[:\s]*(\d+)', section_data["content"])
            if credit_match:
                section_data["minimum_credits"] = int(credit_match.group(1))
            
            core_match = re.search(r'Core Course[s]?[:\s]*(\d+)', section_data["content"])
            if core_match:
                section_data["core_credits"] = int(core_match.group(1))
            
            elective_match = re.search(r'Elective Course[s]?[:\s]*(\d+)', section_data["content"])
            if elective_match:
                section_data["elective_credits"] = int(elective_match.group(1))
        
        # For APPLICATION, extract deadlines and fee
        if "APPLICATION" in section_title.upper():
            if include_deadlines:
                deadlines = extract_deadlines(section_data["content"])
                if deadlines:
                    section_data["deadlines"] = deadlines
            
            # Extract application fee
            fee_match = re.search(r'Application Fee[:\s]*HK\$(\d[\d,]*)', section_data["content"])
            if fee_match:
                section_data["application_fee"] = f"HK${fee_match.group(1)}"
        
        sections[section_title] = section_data
    
    return sections


def extract_deadlines(content: str) -> dict:
    """Extract application deadlines from content"""
    deadlines = {}
    
    # Look for deadline patterns
    lines = content.split('\n')
    
    current_category = None
    for i, line in enumerate(lines):
        line = line.strip()
        
        if 'Non-local' in line and 'Applicant' in line:
            current_category = 'non_local'
            deadlines[current_category] = {}
        elif 'Local' in line and 'Applicant' in line:
            current_category = 'local'
            deadlines[current_category] = {}
        elif current_category and ('Full-time' in line or 'Part-time' in line):
            # Parse deadline line like "Full-time: 1 Mar 2026"
            match = re.match(r'(Full-time|Part-time)[:\s]+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', line)
            if match:
                mode = match.group(1).lower().replace('-', '_')
                date = match.group(2)
                deadlines[current_category][mode] = date
    
    # Also try regex for general deadline extraction
    if not deadlines:
        # Alternative pattern matching
        patterns = [
            (r'(Full-time)[:\s]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', 'full_time'),
            (r'(Part-time)[:\s]*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', 'part_time'),
        ]
        
        for pattern, key in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if key not in deadlines:
                    deadlines[key] = match[1]
    
    return deadlines if deadlines else None


def parse_basic_info(content: str) -> dict:
    """Parse general information into structured fields"""
    info = {}
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if 'Award Title' in line and 'Chinese' not in line:
            info['award_title_en'] = lines[i+1].strip() if i+1 < len(lines) else None
        elif 'Award Title (Chinese)' in line:
            info['award_title_zh'] = lines[i+1].strip() if i+1 < len(lines) else None
        elif 'Program Short Name' in line:
            info['short_name'] = lines[i+1].strip() if i+1 < len(lines) else None
        elif 'Mode of Study' in line:
            info['mode_of_study'] = lines[i+1].strip() if i+1 < len(lines) else None
        elif 'Normative Program Duration' in line:
            duration = []
            j = i + 1
            while j < len(lines) and lines[j].strip() and 'Program Fee' not in lines[j] and 'Offering' not in lines[j]:
                duration.append(lines[j].strip())
                j += 1
            info['duration'] = '\n'.join(duration)
        elif 'Program Fee' in line:
            fee_line = lines[i+1].strip() if i+1 < len(lines) else ''
            info['program_fee'] = fee_line
            # Parse numeric value
            fee_match = re.search(r'HK\$(\d[\d,]*)', fee_line)
            if fee_match:
                info['program_fee_numeric'] = int(fee_match.group(1).replace(',', ''))
        elif 'Website' in line:
            info['website'] = lines[i+1].strip() if i+1 < len(lines) else None
        elif 'Enquiry' in line:
            info['enquiry_email'] = lines[i+1].strip() if i+1 < len(lines) else None
        
        i += 1
    
    return info


def parse_admission_requirements(content: str) -> dict:
    """Parse admission requirements into structured fields"""
    requirements = {
        "general": None,
        "english_language": None,
        "other": None
    }
    
    # Extract general requirements
    if "General Admission Requirements" in content:
        start = content.find("General Admission Requirements")
        end = content.find("English Language", start)
        if end == -1:
            end = content.find("2.", start)
        if start != -1:
            requirements["general"] = content[start:end].strip() if end != -1 else content[start:].strip()
    
    # Extract English language requirements
    if "English Language" in content:
        start = content.find("English Language")
        # Extract TOEFL/IELTS scores
        toefl_match = re.search(r'TOEFL-iBT[:\s]*(\d+)', content)
        ielts_match = re.search(r'IELTS[^(]*\([^)]*\):\s*Overall score[:\s]*([\d.]+)', content)
        
        english_reqs = {}
        if toefl_match:
            english_reqs["toefl_ibt"] = int(toefl_match.group(1))
        if ielts_match:
            english_reqs["ielts_overall"] = float(ielts_match.group(1))
        
        if english_reqs:
            requirements["english_language"] = english_reqs
    
    # Extract other requirements
    if "GMAT" in content or "GRE" in content or "work experience" in content.lower():
        requirements["other"] = "See full requirements for details on GMAT/GRE and work experience"
    
    return requirements


def parse_application_info(application_section: dict) -> dict:
    """Parse application information including fees and deadlines"""
    info = {}
    
    content = application_section.get("content", "")
    
    # Application fee
    fee_match = re.search(r'Application Fee[:\s]*HK\$(\d[\d,]*)', content)
    if fee_match:
        info["application_fee"] = f"HK${fee_match.group(1)}"
        info["application_fee_numeric"] = int(fee_match.group(1).replace(',', ''))
    
    # Deadlines from pre-parsed section
    if "deadlines" in application_section:
        info["deadlines"] = application_section["deadlines"]
    
    # Online application link
    if "Apply online" in content:
        info["application_method"] = "Online"
    
    return info


async def list_programs(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List available postgraduate programs for a given academic year and level.
    
    Note: This function returns a link to the program catalog as the site uses 
    JavaScript navigation.
    """
    academic_year = params.get("academic_year", "2026-27")
    level = params.get("level", "pgprog")  # pgprog for postgraduate
    
    catalog_url = f"https://prog-crs.hkust.edu.hk/{level}/{academic_year}/"
    
    return {
        "success": True,
        "message": "The HKUST program catalog uses JavaScript navigation. "
                   "Please visit the catalog URL to browse available programs.",
        "catalog_url": catalog_url,
        "academic_year": academic_year,
        "note": "Use 'get_program' with a specific program code (e.g., 'msc-fofb', 'msc-mark') "
                "or URL to retrieve detailed program information."
    }


async def search_courses(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for courses within a specific program.
    
    This is a convenience function that retrieves the curriculum section from a program.
    """
    program_result = await get_program(params, ctx)
    
    if not program_result.get("success"):
        return program_result
    
    sections = program_result.get("data", {}).get("sections", {})
    curriculum = sections.get("CURRICULUM", {})
    
    if not curriculum:
        return {
            "success": False,
            "error": "No curriculum section found for this program",
            "url": program_result.get("url")
        }
    
    # Filter courses if search term provided
    search_term = params.get("search_term", "").lower()
    courses = curriculum.get("courses", [])
    
    if search_term:
        courses = [
            c for c in courses
            if search_term in c.get("code", "").lower() or search_term in c.get("name", "").lower()
        ]
    
    return {
        "success": True,
        "url": program_result.get("url"),
        "program_title": program_result.get("data", {}).get("title"),
        "total_courses": len(curriculum.get("courses", [])),
        "matched_courses": len(courses),
        "courses": courses,
        "credit_info": {
            "minimum_credits": curriculum.get("minimum_credits"),
            "core_credits": curriculum.get("core_credits"),
            "elective_credits": curriculum.get("elective_credits")
        }
    }