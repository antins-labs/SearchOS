"""
UCAS Course Access Skill
Fetches course details from UCAS (Universities and Colleges Admissions Service)
"""

import asyncio
import httpx
import json
import re
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Optional


async def execute(params: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """
    Main entry point for UCAS course access
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Context object (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if function == "get_course":
        return await get_course(params)
    elif function == "search_courses":
        return await search_courses(params)
    else:
        return {
            "error": True,
            "message": f"Unknown function: {function}. Use 'get_course' or 'search_courses'"
        }


async def get_course(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch a specific course by ID from UCAS
    """
    course_id = params.get("course_id")
    course_slug = params.get("course_slug", "")
    
    if not course_id:
        return {
            "error": True,
            "message": "course_id is required"
        }
    
    # Validate course_id format (UUID)
    uuid_pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', re.I)
    if not uuid_pattern.match(course_id):
        return {
            "error": True,
            "message": "Invalid course_id format. Expected UUID format."
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Build URL
            url = f"https://www.ucas.com/explore/courses/{course_id}"
            if course_slug:
                url += f"/{course_slug}"
            
            # Fetch course page HTML
            response = await client.get(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
                }
            )
            
            if response.status_code != 200:
                return {
                    "error": True,
                    "message": f"Failed to fetch course page. Status: {response.status_code}"
                }
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Initialize course data
            course_data = {
                "course_id": course_id,
                "url": url
            }
            
            # Extract title
            title_elem = soup.find('h1')
            if title_elem:
                course_data['title'] = title_elem.get_text(strip=True)
            
            # Extract provider information
            provider_link = soup.find('a', href=re.compile(r'/providers/'))
            if provider_link:
                course_data['provider'] = provider_link.get_text(strip=True)
            
            # Extract course details section
            course_details = soup.find(lambda tag: tag.name in ['div', 'section'] and 
                                       'course' in tag.get_text().lower()[:50] and
                                       'details' in tag.get_text().lower()[:200])
            if course_details:
                course_data['course_details_snippet'] = course_details.get_text(strip=True)[:500]
            
            # Extract main content sections
            sections_to_find = [
                ('course_summary', 'Course summary'),
                ('entry_requirements', 'Entry requirements'),
                ('fees_and_funding', 'Fees and funding'),
                ('sponsorship_information', 'Sponsorship information'),
                ('study_options', 'Study options'),
                ('campuses', 'Campuses'),
                ('contact_details', 'Course contact details'),
            ]
            
            for section_key, section_name in sections_to_find:
                heading = soup.find(
                    lambda tag: tag.name in ['h2', 'h3', 'h4'] and 
                    section_name.lower() in tag.get_text().lower()
                )
                if heading:
                    content = []
                    for sibling in heading.find_next_siblings():
                        if sibling.name in ['h2', 'h3', 'h4']:
                            break
                        text = sibling.get_text(strip=True)
                        # Filter out navigation elements
                        if text and text not in ['Course options', 'Find out more', 'Related courses']:
                            content.append(text)
                    
                    if content:
                        course_data[section_key] = ' '.join(content)[:2000]  # Limit content length
            
            # Extract contact information
            email_link = soup.find('a', href=re.compile(r'^mailto:'))
            if email_link:
                course_data['contact_email'] = email_link.get('href').replace('mailto:', '')
            
            phone_link = soup.find('a', href=re.compile(r'^tel:'))
            if phone_link:
                course_data['contact_phone'] = phone_link.get('href').replace('tel:', '')
            
            # Also fetch data from Algolia for structured information
            # Use title from page if available
            title = course_data.get('title', '')
            algolia_data = await _fetch_from_algolia(client, course_id, title)
            if algolia_data:
                course_data['structured_data'] = algolia_data
                
                # Add important fields directly to course_data for convenience
                if algolia_data.get('provider'):
                    course_data['provider'] = algolia_data['provider'].get('name', course_data.get('provider', ''))
                if algolia_data.get('studyLevel'):
                    course_data['study_level'] = algolia_data['studyLevel']
                if algolia_data.get('outcomeQualification'):
                    course_data['qualification'] = algolia_data['outcomeQualification'].get('name')
            
            # Fetch unistats if we have a course option ID
            if algolia_data and algolia_data.get('courseOptionId'):
                unistats = await _fetch_unistats(
                    client, 
                    course_id, 
                    algolia_data.get('courseOptionId'),
                    algolia_data.get('academicYearId', '2026')
                )
                if unistats:
                    course_data['unistats'] = unistats
            
            return {
                "error": False,
                "course": course_data
            }
            
    except httpx.TimeoutException:
        return {
            "error": True,
            "message": "Request timed out"
        }
    except Exception as e:
        return {
            "error": True,
            "message": f"Error fetching course: {str(e)}"
        }


async def search_courses(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for courses on UCAS using Algolia
    """
    query = params.get("query", "")
    provider = params.get("provider")
    study_level = params.get("study_level")
    max_results = params.get("max_results", 20)
    
    if not query and not provider:
        return {
            "error": True,
            "message": "At least one of 'query' or 'provider' is required"
        }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Build Algolia query
            search_params = []
            
            if query:
                search_params.append(f"query={query}")
            
            # Add filters
            filters = []
            if provider:
                filters.append(f'provider.name:"{provider}"')
            if study_level:
                filters.append(f'studyLevel:"{study_level}"')
            
            if filters:
                search_params.append(f"filters={' AND '.join(filters)}")
            
            search_params.append(f"hitsPerPage={min(max_results, 100)}")
            
            # Query Algolia
            response = await client.post(
                "https://y3qrv216kl-dsn.algolia.net/1/indexes/d10prod_courses_new/query",
                headers={
                    'X-Algolia-API-Key': 'c0f72e5c62250ac258c2cf4a3896c19d',
                    'X-Algolia-Application-Id': 'Y3QRV216KL',
                    'Content-Type': 'application/json',
                },
                json={
                    "params": "&".join(search_params)
                }
            )
            
            if response.status_code != 200:
                return {
                    "error": True,
                    "message": f"Search failed with status {response.status_code}"
                }
            
            data = response.json()
            
            # Format results
            courses = []
            for hit in data.get('hits', []):
                course = {
                    'course_id': hit.get('courseId'),
                    'title': hit.get('courseTitle'),
                    'provider': hit.get('provider', {}).get('name'),
                    'provider_id': hit.get('provider', {}).get('providerId'),
                    'qualification': hit.get('outcomeQualification', {}).get('name'),
                    'study_level': hit.get('studyLevel'),
                    'study_mode': hit.get('studyMode', {}).get('caption'),
                    'duration': hit.get('duration', {}).get('caption'),
                    'location': hit.get('location', {}).get('name'),
                    'town_or_city': hit.get('location', {}).get('townOrCity'),
                    'country': hit.get('location', {}).get('country', {}).get('original'),
                    'region': hit.get('location', {}).get('region', {}).get('original'),
                    'start_date': f"{hit.get('startDate', {}).get('month', '')} {hit.get('startDate', {}).get('year', '')}",
                    'subjects': [s.get('name') for s in hit.get('searchSubjects', [])],
                    'url': f"https://www.ucas.com/explore/courses/{hit.get('courseId')}",
                }
                courses.append(course)
            
            return {
                "error": False,
                "total_results": data.get('nbHits', 0),
                "results_count": len(courses),
                "courses": courses
            }
            
    except httpx.TimeoutException:
        return {
            "error": True,
            "message": "Search request timed out"
        }
    except Exception as e:
        return {
            "error": True,
            "message": f"Error searching courses: {str(e)}"
        }


async def _fetch_from_algolia(client: httpx.AsyncClient, course_id: str, title: str = "") -> Optional[Dict]:
    """
    Fetch course data from Algolia API using title-based search
    """
    try:
        # Clean up title for search (remove "(Taught)", "(Degree)", etc.)
        search_title = re.sub(r'\s*\([^)]+\)\s*', ' ', title).strip()
        
        # Search by title
        response = await client.post(
            "https://y3qrv216kl-dsn.algolia.net/1/indexes/d10prod_courses_new/query",
            headers={
                'X-Algolia-API-Key': 'c0f72e5c62250ac258c2cf4a3896c19d',
                'X-Algolia-Application-Id': 'Y3QRV216KL',
                'Content-Type': 'application/json',
            },
            json={
                "params": f"query={search_title}&hitsPerPage=20"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            # Find exact match by courseId
            for hit in data.get('hits', []):
                if hit.get('courseId') == course_id:
                    return hit
        
        return None
    except:
        return None


async def _fetch_unistats(client: httpx.AsyncClient, course_id: str, 
                          course_option_id: str, academic_year: str = "2026") -> Optional[Dict]:
    """
    Fetch course statistics from UCAS unistats API
    """
    try:
        params = {
            "courses[0][courseId]": course_id,
            "courses[0][academicYearId]": academic_year,
            "courses[0][courseOptionId]": course_option_id
        }
        
        response = await client.get(
            "https://www.ucas.com/api/v1/unistats",
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('results'):
                return data['results'][0]
        
        return None
    except:
        return None


if __name__ == "__main__":
    # Test the module
    import sys
    
    async def test():
        # Test get_course
        print("Testing get_course...")
        result = await execute({
            "function": "get_course",
            "course_id": "18f73fdf-0804-2e30-cf22-f66710164e4f",
            "course_slug": "media-and-communication"
        }, None)
        print(json.dumps(result, indent=2))
        
        print("\n" + "="*80 + "\n")
        
        # Test search
        print("Testing search_courses...")
        result = await execute({
            "function": "search_courses",
            "query": "journalism",
            "max_results": 5
        }, None)
        print(json.dumps(result, indent=2)[:3000])
    
    asyncio.run(test())