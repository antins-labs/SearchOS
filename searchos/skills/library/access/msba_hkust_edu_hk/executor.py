"""
HKUST MSBA (Master of Science in Business Analytics) Access Skill

This skill provides structured access to admission information, program details,
fees, curriculum, and other relevant data from the HKUST MSBA program website.
"""

import aiohttp
import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class ProgramFee:
    """Program fee information"""
    intake_year: str
    tuition_fee_hkd: str
    caution_money_hkd: str
    graduation_fee_hkd: str
    visa_fee_hkd: str
    notes: list[str]


@dataclass
class AdmissionRequirement:
    """Admission requirement details"""
    category: str
    details: list[str]


@dataclass
class ApplicationDeadline:
    """Application deadline information"""
    phase: str
    full_time_deadline: Optional[str]
    part_time_deadline: Optional[str]
    year: str


@dataclass
class Scholarship:
    """Scholarship information"""
    name: str
    description: str
    amount: str


@dataclass
class Course:
    """Course information"""
    code: Optional[str]
    name: str
    category: str  # Required or Elective


class HKUSTMSBAScraper:
    """Scraper for HKUST MSBA program website"""
    
    BASE_URL = "https://msba.hkust.edu.hk"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: dict[str, tuple[datetime, str]] = {}
        self.cache_duration = 3600  # 1 hour cache
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def _fetch_page(self, path: str) -> str:
        """Fetch a page with caching"""
        cache_key = path
        now = datetime.now()
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_content = self.cache[cache_key]
            if (now - cached_time).total_seconds() < self.cache_duration:
                return cached_content
        
        # Fetch from web
        session = await self._get_session()
        url = f"{self.BASE_URL}{path}"
        
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.text()
            
        # Cache the result
        self.cache[cache_key] = (now, content)
        return content
    
    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text
    
    def _extract_course_title(self, text: str) -> str:
        """Extract just the course title from text that may include description"""
        # Remove [See video preview] and similar
        text = re.sub(r'\[.*?\]', '', text).strip()
        # Remove video links
        text = re.sub(r'https?://\S+', '', text).strip()
        # Get only first line if there are newlines
        lines = text.split('\n')
        if lines:
            text = lines[0].strip()
        # If very long, likely includes description - extract just title
        if len(text) > 100:
            # Try to find natural break points
            for delimiter in ['. ', 'This course', 'In this course', 'Covers ', 'Students will']:
                if delimiter in text:
                    idx = text.find(delimiter)
                    if idx > 20:  # Ensure we keep at least some title
                        text = text[:idx].strip()
                        break
            # If still too long, truncate at first sentence
            if len(text) > 100 and '. ' in text:
                text = text.split('. ')[0].strip()
        return text
    
    async def get_program_fees(self) -> dict[str, Any]:
        """Extract program fee and expense information"""
        try:
            html = await self._fetch_page('/admission/program-fee-expenses')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            text = content.get_text() if content else ""
            
            fees = ProgramFee(
                intake_year="2027/28",
                tuition_fee_hkd="415,000",
                caution_money_hkd="400",
                graduation_fee_hkd="400",
                visa_fee_hkd="1,000",
                notes=[]
            )
            
            # Extract tuition fee
            tuition_match = re.search(r'total program fee.*?HK\$\s*([\d,]+)', text, re.IGNORECASE)
            if tuition_match:
                fees.tuition_fee_hkd = tuition_match.group(1)
            
            # Extract intake year
            year_match = re.search(r'(\d{4}/\d{2})\s+intake', text)
            if year_match:
                fees.intake_year = year_match.group(1)
            
            # Extract caution money
            caution_match = re.search(r'caution money.*?HK\$(\d+)', text, re.IGNORECASE)
            if caution_match:
                fees.caution_money_hkd = caution_match.group(1)
            
            # Extract graduation fee
            grad_match = re.search(r'graduation fee.*?HK\$(\d+)', text, re.IGNORECASE)
            if grad_match:
                fees.graduation_fee_hkd = grad_match.group(1)
            
            # Extract visa fee
            visa_match = re.search(r'HK\$(\d+[\d,]*)\s*will be charged.*?visa', text, re.IGNORECASE | re.DOTALL)
            if visa_match:
                fees.visa_fee_hkd = visa_match.group(1)
            
            # Extract notes about what's included/excluded
            if 'excludes books' in text.lower():
                fees.notes.append("Program fee excludes books, computer equipment, software licensing")
            if 'medical insurance' in text.lower():
                fees.notes.append("Compulsory medical insurance required for non-local students")
            
            return {
                "success": True,
                "data": asdict(fees),
                "source_url": f"{self.BASE_URL}/admission/program-fee-expenses"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_admission_requirements(self) -> dict[str, Any]:
        """Extract admission requirements"""
        try:
            html = await self._fetch_page('/admission/admission-requirements')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            requirements = []
            
            # Look for requirement sections
            h3_tags = content.find_all('h3') if content else []
            
            for h3 in h3_tags:
                heading_text = self._clean_text(h3.get_text())
                
                # Skip non-requirement headings
                if not any(keyword in heading_text.lower() for keyword in 
                          ['degree', 'english', 'gmat', 'gre', 'work', 'programming', 'proficiency']):
                    continue
                
                # Get the content after this heading until the next heading
                requirement_details = []
                sibling = h3.find_next_sibling()
                
                while sibling and sibling.name not in ['h2', 'h3']:
                    if sibling.name in ['p', 'ul', 'ol']:
                        text = self._clean_text(sibling.get_text())
                        if text:
                            # Split by newlines or bullet points
                            items = re.split(r'\n+|\s*•\s*', text)
                            requirement_details.extend([item.strip() for item in items if item.strip()])
                    sibling = sibling.find_next_sibling()
                
                requirements.append(AdmissionRequirement(
                    category=heading_text,
                    details=requirement_details[:10]  # Limit to 10 items
                ))
            
            # Also extract key requirements from overall text
            text = content.get_text() if content else ""
            
            # Extract specific requirements
            key_requirements = {}
            
            # TOEFL requirement
            toefl_match = re.search(r'TOEFL.*?(\d+).*?iBT', text, re.IGNORECASE | re.DOTALL)
            if toefl_match:
                key_requirements['toefl_min'] = toefl_match.group(1)
            
            # IELTS requirement
            ielts_match = re.search(r'IELTS.*?(\d+\.?\d*).*?overall', text, re.IGNORECASE | re.DOTALL)
            if ielts_match:
                key_requirements['ielts_min'] = ielts_match.group(1)
            
            return {
                "success": True,
                "data": {
                    "requirements": [asdict(r) for r in requirements],
                    "key_requirements": key_requirements,
                    "overview": self._clean_text(text[:1000]) if text else ""
                },
                "source_url": f"{self.BASE_URL}/admission/admission-requirements"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_application_schedule(self) -> dict[str, Any]:
        """Extract application deadlines and procedures"""
        try:
            html = await self._fetch_page('/admission/application-schedule-procedures')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            text = content.get_text() if content else ""
            
            deadlines = []
            
            # Extract year
            year_match = re.search(r'(\d{4}/\d{2})\s+intake', text)
            intake_year = year_match.group(1) if year_match else "2027/28"
            
            # Parse full-time deadlines
            full_time_section = re.search(r'FULL[- ]?TIME.*?(?=PART[- ]?TIME|$)', text, re.IGNORECASE | re.DOTALL)
            part_time_section = re.search(r'PART[- ]?TIME.*?(?=\n[A-Z]{2,}|$)', text, re.IGNORECASE | re.DOTALL)
            
            # Extract phases
            phases = ['Phase 1', 'Phase 2', 'Phase 3', 'Phase 4']
            
            for i, phase in enumerate(phases):
                deadline = ApplicationDeadline(
                    phase=phase,
                    full_time_deadline=None,
                    part_time_deadline=None,
                    year=intake_year
                )
                
                # Try to extract full-time deadline
                if full_time_section:
                    ft_matches = re.findall(rf'{phase}.*?([A-Z][a-z]+\s+\d{{1,2}})', full_time_section.group(0), re.DOTALL)
                    if ft_matches:
                        deadline.full_time_deadline = self._clean_text(ft_matches[0])
                
                # Try to extract part-time deadline
                if part_time_section:
                    pt_matches = re.findall(rf'{phase}.*?([A-Z][a-z]+\s+\d{{1,2}})', part_time_section.group(0), re.DOTALL)
                    if pt_matches:
                        deadline.part_time_deadline = self._clean_text(pt_matches[0])
                
                deadlines.append(asdict(deadline))
            
            # Extract application steps
            steps = []
            step_pattern = re.compile(r'Step\s+(\d+):\s*([^\n]+)', re.IGNORECASE)
            for match in step_pattern.finditer(text):
                steps.append({
                    "step_number": match.group(1),
                    "title": self._clean_text(match.group(2))
                })
            
            return {
                "success": True,
                "data": {
                    "intake_year": intake_year,
                    "deadlines": deadlines,
                    "application_steps": steps,
                    "rolling_admissions": "rolling" in text.lower()
                },
                "source_url": f"{self.BASE_URL}/admission/application-schedule-procedures"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_scholarships(self) -> dict[str, Any]:
        """Extract scholarship and financial aid information"""
        try:
            html = await self._fetch_page('/admission/scholarship-financial-aids')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            scholarships = []
            
            # Look for scholarship sections
            h3_tags = content.find_all('h3') if content else []
            
            for h3 in h3_tags:
                name = self._clean_text(h3.get_text())
                
                # Skip non-scholarship headings
                if not name or len(name) < 5:
                    continue
                
                # Get description
                description_parts = []
                sibling = h3.find_next_sibling()
                
                while sibling and sibling.name not in ['h2', 'h3']:
                    if sibling.name == 'p':
                        text = self._clean_text(sibling.get_text())
                        if text:
                            description_parts.append(text)
                    sibling = sibling.find_next_sibling()
                    if len(description_parts) >= 2:
                        break
                
                description = ' '.join(description_parts)
                
                # Extract amount
                amount = "Not specified"
                amount_match = re.search(r'HK\$\s*([\d,]+)', description)
                if amount_match:
                    amount = f"HK${amount_match.group(1)}"
                elif 'half' in description.lower():
                    amount = "Up to half of tuition fees"
                
                scholarships.append(Scholarship(
                    name=name,
                    description=description[:500] if description else "",
                    amount=amount
                ))
            
            return {
                "success": True,
                "data": {
                    "scholarships": [asdict(s) for s in scholarships],
                    "total_scholarships": len(scholarships)
                },
                "source_url": f"{self.BASE_URL}/admission/scholarship-financial-aids"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_curriculum(self) -> dict[str, Any]:
        """Extract program curriculum and course information"""
        try:
            html = await self._fetch_page('/program/program-curriculum')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            text = content.get_text() if content else ""
            
            required_courses = []
            elective_courses = []
            
            # Find all h3 headings
            h3_tags = content.find_all('h3') if content else []
            
            for h3 in h3_tags:
                heading_text = self._clean_text(h3.get_text()).lower()
                
                # Handle "Course Descriptions" separately - we already have the courses listed above
                if 'course descriptions' in heading_text:
                    continue
                
                if 'required courses' in heading_text:
                    # Get the next sibling which should be a UL
                    next_elem = h3.find_next_sibling()
                    if next_elem and next_elem.name == 'ul':
                        list_items = next_elem.find_all('li')
                        for li in list_items:
                            course_text = self._clean_text(li.get_text())
                            course_title = self._extract_course_title(course_text)
                            if course_title and len(course_title) > 3 and len(course_title) < 150:
                                required_courses.append(Course(
                                    code=None,
                                    name=course_title,
                                    category="Required"
                                ))
                
                elif 'elective courses' in heading_text or 'ai strategy track' in heading_text or 'track' in heading_text:
                    # Get the next sibling which should be a UL
                    next_elem = h3.find_next_sibling()
                    if next_elem and next_elem.name == 'ul':
                        list_items = next_elem.find_all('li')
                        for li in list_items:
                            course_text = self._clean_text(li.get_text())
                            course_title = self._extract_course_title(course_text)
                            if course_title and len(course_title) > 3 and len(course_title) < 150:
                                elective_courses.append(Course(
                                    code=None,
                                    name=course_title,
                                    category="Elective"
                                ))
            
            # Extract credit requirements
            credits_match = re.search(r'(\d+)\s+credits', text)
            total_credits = credits_match.group(1) if credits_match else "30"
            
            # More precise credit extraction
            required_credits_match = re.search(r'(\d+)\s+credits.*?Required\s+Courses', text, re.IGNORECASE)
            required_credits = required_credits_match.group(1) if required_credits_match else "16"
            
            elective_credits_match = re.search(r'(\d+)\s+credits.*?Elective\s+Courses', text, re.IGNORECASE)
            elective_credits = elective_credits_match.group(1) if elective_credits_match else "14"
            
            return {
                "success": True,
                "data": {
                    "total_credits": total_credits,
                    "required_credits": required_credits,
                    "elective_credits": elective_credits,
                    "required_courses": [asdict(c) for c in required_courses],
                    "elective_courses": [asdict(c) for c in elective_courses],
                    "has_consulting_track": "consulting" in text.lower(),
                    "total_required_courses": len(required_courses),
                    "total_elective_courses": len(elective_courses)
                },
                "source_url": f"{self.BASE_URL}/program/program-curriculum"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_program_overview(self) -> dict[str, Any]:
        """Extract program overview and schedule information"""
        try:
            html = await self._fetch_page('/program/overview-schedule')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            text = content.get_text() if content else ""
            
            # Extract key information
            overview = {
                "program_modes": [],
                "duration": {},
                "campus": "HKUST Clear Water Bay Campus",
                "features": []
            }
            
            # Check for full-time and part-time
            if 'full-time' in text.lower():
                overview["program_modes"].append("Full-time")
                overview["duration"]["full_time"] = "1 year"
            if 'part-time' in text.lower():
                overview["program_modes"].append("Part-time")
                overview["duration"]["part_time"] = "2 years"
            
            # Extract features
            if 'design thinking' in text.lower():
                overview["features"].append("Design thinking workshops")
            if 'consulting' in text.lower():
                overview["features"].append("Corporate consulting track")
            if 'corporate advisory board' in text.lower():
                overview["features"].append("Corporate Advisory Board")
            if 'workshop' in text.lower():
                overview["features"].append("Professional workshops")
            
            return {
                "success": True,
                "data": overview,
                "source_url": f"{self.BASE_URL}/program/overview-schedule"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def get_class_profile(self) -> dict[str, Any]:
        """Extract class profile statistics"""
        try:
            html = await self._fetch_page('/student-life/class-profile')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find main content area
            content = soup.find('div', class_='layout-content') or soup.find('article')
            if not content:
                content = soup.find('body')
            
            text = content.get_text() if content else ""
            
            profile = {
                "year": None,
                "statistics": {}
            }
            
            # Extract year
            year_match = re.search(r'(\d{4}[-–]\d{2,4})', text)
            if year_match:
                profile["year"] = year_match.group(1)
            
            # Extract gender ratio
            gender_match = re.search(r'Gender Ratio.*?(\d+)\s*[:/]\s*(\d+)', text, re.IGNORECASE | re.DOTALL)
            if gender_match:
                profile["statistics"]["gender_ratio"] = f"{gender_match.group(1)}:{gender_match.group(2)} (Female:Male)"
            
            # Extract countries represented
            countries_match = re.search(r'(\d+)\s*Countries', text, re.IGNORECASE)
            if countries_match:
                profile["statistics"]["countries_represented"] = countries_match.group(1)
            
            # Extract business vs non-business ratio
            discipline_match = re.search(r'(\d+)\s*[:/]\s*(\d+)\s*[:/]\s*(\d+).*?Business', text, re.IGNORECASE | re.DOTALL)
            if discipline_match:
                profile["statistics"]["degree_disciplines"] = f"{discipline_match.group(1)}:{discipline_match.group(2)}:{discipline_match.group(3)} (Business:Engineering:Others)"
            
            # Extract places of origin
            places_match = re.search(r'(\d+)\s*\|\s*(\d+).*?Countries.*?Regions', text, re.IGNORECASE | re.DOTALL)
            if places_match:
                profile["statistics"]["places_of_origin"] = f"{places_match.group(1)} countries, {places_match.group(2)} regions"
            
            return {
                "success": True,
                "data": profile,
                "source_url": f"{self.BASE_URL}/student-life/class-profile"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    async def search_all(self, query: str) -> dict[str, Any]:
        """Search across all pages for specific information"""
        try:
            query_lower = query.lower()
            results = []
            
            # Define pages to search
            pages = {
                "fees": "/admission/program-fee-expenses",
                "requirements": "/admission/admission-requirements",
                "schedule": "/admission/application-schedule-procedures",
                "scholarships": "/admission/scholarship-financial-aids",
                "curriculum": "/program/program-curriculum",
                "overview": "/program/overview-schedule",
                "class_profile": "/student-life/class-profile"
            }
            
            for page_name, path in pages.items():
                html = await self._fetch_page(path)
                soup = BeautifulSoup(html, 'html.parser')
                content = soup.find('div', class_='layout-content') or soup.find('article') or soup.find('body')
                text = content.get_text() if content else ""
                
                # Search for query in text
                if query_lower in text.lower():
                    # Find relevant snippets
                    snippets = []
                    sentences = re.split(r'[.!?]+', text)
                    for sentence in sentences:
                        if query_lower in sentence.lower():
                            clean = self._clean_text(sentence)
                            if len(clean) > 20:
                                snippets.append(clean[:300])
                    
                    if snippets:
                        results.append({
                            "page": page_name.replace('_', ' ').title(),
                            "url": f"{self.BASE_URL}{path}",
                            "snippets": snippets[:3]
                        })
            
            return {
                "success": True,
                "data": {
                    "query": query,
                    "results": results,
                    "total_matches": len(results)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": None
            }


# Global scraper instance
_scraper: Optional[HKUSTMSBAScraper] = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute HKUST MSBA skill functions.
    
    Args:
        params: Dictionary containing:
            - function: (required) One of:
                - get_program_fees: Get tuition and fee information
                - get_admission_requirements: Get admission requirements
                - get_application_schedule: Get application deadlines
                - get_scholarships: Get scholarship information
                - get_curriculum: Get program curriculum
                - get_program_overview: Get program overview
                - get_class_profile: Get class profile statistics
                - search_all: Search across all pages (requires 'query' parameter)
                - get_all_info: Get comprehensive information summary
            - query: Search query (required for search_all function)
        ctx: Context object (not used)
    
    Returns:
        Dictionary with success status and data or error message
    """
    global _scraper
    
    if "function" not in params:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "data": None
        }
    
    function = params["function"]
    
    # Initialize scraper if needed
    if _scraper is None:
        _scraper = HKUSTMSBAScraper()
    
    try:
        if function == "get_program_fees":
            result = await _scraper.get_program_fees()
        
        elif function == "get_admission_requirements":
            result = await _scraper.get_admission_requirements()
        
        elif function == "get_application_schedule":
            result = await _scraper.get_application_schedule()
        
        elif function == "get_scholarships":
            result = await _scraper.get_scholarships()
        
        elif function == "get_curriculum":
            result = await _scraper.get_curriculum()
        
        elif function == "get_program_overview":
            result = await _scraper.get_program_overview()
        
        elif function == "get_class_profile":
            result = await _scraper.get_class_profile()
        
        elif function == "search_all":
            if "query" not in params:
                return {
                    "success": False,
                    "error": "Missing required parameter: query",
                    "data": None
                }
            result = await _scraper.search_all(params["query"])
        
        elif function == "get_all_info":
            # Get comprehensive information
            fees_task = _scraper.get_program_fees()
            requirements_task = _scraper.get_admission_requirements()
            schedule_task = _scraper.get_application_schedule()
            scholarships_task = _scraper.get_scholarships()
            overview_task = _scraper.get_program_overview()
            
            fees, requirements, schedule, scholarships, overview = await asyncio.gather(
                fees_task, requirements_task, schedule_task, scholarships_task, overview_task
            )
            
            result = {
                "success": True,
                "data": {
                    "program_fees": fees.get("data"),
                    "admission_requirements": requirements.get("data"),
                    "application_schedule": schedule.get("data"),
                    "scholarships": scholarships.get("data"),
                    "program_overview": overview.get("data")
                }
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "data": None
            }
        
        return result
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Execution error: {str(e)}",
            "data": None
        }