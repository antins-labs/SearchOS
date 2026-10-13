"""
Hiroshima National Peace Memorial Hall for the Atomic Bomb Victims
Access skill for www.hiro-tsuitokinenkan.go.jp

This skill provides structured access to facility information, visiting details,
floor guides, FAQ, and institutional data from the English section of the site.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import re


BASE_URL = "https://www.hiro-tsuitokinenkan.go.jp/en"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(session: aiohttp.ClientSession, path: str) -> str:
    """Fetch HTML content from a given path."""
    url = f"{BASE_URL}{path}"
    async with session.get(url, headers=HEADERS, timeout=30) as response:
        response.raise_for_status()
        return await response.text()


def extract_main_content(html: str) -> str:
    """Extract main content text from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    if main:
        return main.get_text(separator='\n', strip=True)
    return ""


def clean_text(text: str) -> str:
    """Clean up extracted text."""
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


async def get_homepage(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get homepage with opening hours, notices, and main features."""
    html = await fetch_page(session, "/")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "Hiroshima National Peace Memorial Hall for the Atomic Bomb Victims",
        "url": f"{BASE_URL}/",
        "sections": {}
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Extract opening hours
        hours_match = re.search(r"Today's Opening Hours\s*(\d+:\d+-\d+:\d+)", text)
        if hours_match:
            result["sections"]["opening_hours_today"] = hours_match.group(1)
        
        # Extract notices
        notices = []
        notice_section = re.search(r'Notice(.*?)(?:To the|List of Previous)', text, re.DOTALL)
        if notice_section:
            notice_text = notice_section.group(1)
            # Parse individual notices (date + title pattern)
            notice_items = re.findall(r'(\d{4}/\d{2}/\d{2})\s*\n?\s*([^\n]+)', notice_text)
            for date, title in notice_items:
                notices.append({"date": date, "title": title.strip()})
        result["sections"]["notices"] = notices
        
        # Extract main features
        features = []
        feature_keywords = [
            "Registering Victims", "Atomic Bomb Memoirs", "Special Exhibitions",
            "Atomic Bomb Memoir Readings", "Survivor Testimony Videos",
            "Translation of Testimony", "Short Film Introduction"
        ]
        for kw in feature_keywords:
            if kw in text:
                features.append(kw)
        result["sections"]["main_features"] = features
        
        # Extract calls to action
        if "To the Hibakusha" in text:
            result["sections"]["call_to_action_survivors"] = "Submitting memoirs from bombing survivors"
        if "To the Bereaved Families" in text:
            result["sections"]["call_to_action_families"] = "Registering names and photographs of victims"
        if "To Educators" in text:
            result["sections"]["call_to_action_educators"] = "Peace study programs and educational resources"
    
    return result


async def get_visitor_info(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get visitor information including hours, admission, location, and directions."""
    html = await fetch_page(session, "/visit/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "Directions to the Memorial Hall",
        "url": f"{BASE_URL}/visit/index.html",
        "opening_hours": {},
        "admission": None,
        "location": None,
        "directions": {},
        "facilities": {}
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Extract opening hours by season
        hours_patterns = [
            ("march_to_july", r"March 1-July 31\s*(\d+:\d+\s*[ap]m\s*to\s*\d+:\d+\s*[ap]m)"),
            ("august", r"August 1-August 31\s*(\d+:\d+\s*[ap]m\s*to\s*\d+:\d+\s*[ap]m)"),
            ("september_to_november", r"September 1-November 30\s*(\d+:\d+\s*[ap]m\s*to\s*\d+:\d+\s*[ap]m)"),
            ("december_to_february", r"December 1-End of February\s*(\d+:\d+\s*[ap]m\s*to\s*\d+:\d+\s*[ap]m)"),
        ]
        for key, pattern in hours_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["opening_hours"][key] = match.group(1)
        
        # Extract August special hours
        aug_special = re.search(r"8/5-6 close at (\d+:\d+\s*[ap]m)", text)
        if aug_special:
            result["opening_hours"]["august_5_6_special"] = f"Close at {aug_special.group(1)}"
        
        # Extract closed dates
        closed_match = re.search(r"Closed\s*(December[^\n]+)", text)
        if closed_match:
            result["closed"] = closed_match.group(1).strip()
        
        # Extract admission
        if "Admission Fees" in text:
            result["admission"] = "Free"
        
        # Extract directions
        directions = {}
        
        # From JR Hiroshima Station
        jr_section = re.search(r"From JR Hiroshima Station.*?(?=From Hiroshima Port|$)", text, re.DOTALL)
        if jr_section:
            directions["from_jr_hiroshima_station"] = {
                "bus": "Approx. 20 minutes - No. 24 Hiroshima Bus to Yoshijima, get off at Hon-dori; or Eki-Machi City Loop Bus",
                "streetcar": "Approx. 20 minutes - No. 1 to Hiroshima Port (Ujina), get off at Hon-dori; or No. 2/6 to Genbaku Dome-mae"
            }
        
        # From Hiroshima Port
        port_section = re.search(r"From Hiroshima Port.*?(?=From Hiroshima Airport|$)", text, re.DOTALL)
        if port_section:
            directions["from_hiroshima_port"] = {
                "bus": "Approx. 30 minutes - No. 21 Hiroshima Bus to Hiroshima Station, get off at Hon-dori",
                "streetcar": "Approx. 30 minutes - No. 1 to Hiroshima Station or No. 3 to Nishi-Hiroshima, get off at Hon-dori"
            }
        
        # From Airport
        airport_match = re.search(r"From Hiroshima Airport.*?limousine bus.*?(\d+ [^\n]+)", text, re.DOTALL)
        if airport_match:
            directions["from_hiroshima_airport"] = "Limousine bus approx. 1 hour to Hiroshima Bus Center"
        
        result["directions"] = directions
        
        # Extract parking info
        parking_match = re.search(r"Parking Facilities\s*\n([^\n]+(?:\n[^\n]+)*?)(?=Facilities in|$)", text)
        if parking_match:
            result["parking"] = "No public parking available (except for disabled visitors). Use public parking around Peace Memorial Park."
        
        # Extract facilities
        facilities = {}
        
        if "Wheelchair Rentals" in text:
            wheelchair_match = re.search(r"(\d+)\s*wheelchairs available", text)
            facilities["wheelchair_rental"] = f"{wheelchair_match.group(1) if wheelchair_match else '3'} wheelchairs available free of charge at General Information Desk"
        
        if "Coin-Operated Storage Lockers" in text:
            facilities["lockers"] = {
                "small": "8 lockers (W346mm x D422mm x H370mm)",
                "large": "4 lockers (W346mm x D482mm x H774mm)",
                "deposit": "100 yen (returned after use)"
            }
        
        if "Resting Room" in text:
            facilities["resting_room"] = "Available on Lower Level - Japanese-style tatami room with futons"
        
        result["facilities"] = facilities
    
    return result


async def get_floor_guide(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get floor guide with facility details for each level."""
    html = await fetch_page(session, "/floormap/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "Floor Guide",
        "url": f"{BASE_URL}/floormap/index.html",
        "floors": {}
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Ground Floor
        ground_floor = {}
        if "Ground Floor" in text:
            ground_floor["name"] = "Ground Floor"
            
            # Inscription
            inscription_match = re.search(r"Inscription\s*\n([^\n]+(?:\n[^\n]+)*?)(?=8:15 am Monument|$)", text)
            if inscription_match:
                ground_floor["inscription"] = clean_text(inscription_match.group(1))
            
            # 8:15 am Monument
            monument_match = re.search(r"8:15 am Monument.*?(?=Upper Level|$)", text, re.DOTALL)
            if monument_match:
                monument_text = monument_match.group(0)
                monument_desc = re.search(r"This monument[^\n]+(?:\n[^\n]+)*", monument_text)
                if monument_desc:
                    ground_floor["8_15_monument"] = clean_text(monument_desc.group(0))
        
        result["floors"]["ground_floor"] = ground_floor
        
        # Upper Level
        upper_level = {}
        if "Upper Level" in text:
            upper_level["name"] = "Upper Level"
            
            # Slope to Hall of Remembrance
            slope_match = re.search(r"Slope to the Hall of Remembrance.*?(?=Special Exhibition|$)", text, re.DOTALL)
            if slope_match:
                upper_level["slope_to_hall"] = "Descending counter-clockwise, back in time to Hiroshima just after the bombing. Six panels explain background to atomic bombing."
            
            # Special Exhibition Area
            if "Special Exhibition Area" in text:
                upper_level["special_exhibition_area"] = "30-minute film presentation on large projection screen. Special exhibitions introduce atomic bomb memoirs."
            
            # Library
            if "Library" in text:
                library_match = re.search(r"Library.*?Over 140,000 memoirs", text, re.DOTALL)
                if library_match:
                    upper_level["library"] = {
                        "description": "Materials search terminals available",
                        "materials": [
                            "Over 140,000 memoirs by survivors and bereaved families",
                            "Atomic bomb survivor testimonies",
                            "Photos of Hiroshima before and after bombing",
                            "Video footage from after the bombing",
                            "Other atomic bomb related materials"
                        ],
                        "languages": "Touch screen databases in English, Chinese, Korean, Japanese. Selected materials in 20+ languages."
                    }
            
            # Stratum Cross-Section
            if "Stratum Cross-Section" in text:
                upper_level["stratum_cross_section"] = "Excavation survey showing ground beneath Peace Memorial Park"
        
        result["floors"]["upper_level"] = upper_level
        
        # Lower Level
        lower_level = {}
        if "Lower Level" in text:
            lower_level["name"] = "Lower Level"
            
            # Hall of Remembrance
            hall_match = re.search(r"Hall of Remembrance.*?(?=Victims' Information|$)", text, re.DOTALL)
            if hall_match:
                lower_level["hall_of_remembrance"] = {
                    "description": "Space for quiet reflection and prayer for peace",
                    "features": [
                        "360° panoramic photo of Hiroshima after bombing from hypocenter (Shima Hospital)",
                        "Approximately 140,000 tiles (estimated deaths by end of 1945)",
                        "Names of 226 towns that existed at time of bombing",
                        "Dimensions: 55m perimeter, 17.25m diameter, 8m ceiling height"
                    ],
                    "central_monument": "Displays 8:15 am bombing time with water fountain to console victims"
                }
            
            # Victims' Information Area
            if "Victims' Information Area" in text:
                lower_level["victims_information_area"] = {
                    "description": "Names and portraits of victims displayed on loop",
                    "search_available": "Visitors can search for individual names and portraits via terminals"
                }
        
        result["floors"]["lower_level"] = lower_level
        
        # Google Street View
        if "Google Map Streetview" in text:
            result["google_street_view_available"] = True
    
    return result


async def get_about_info(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get information about the Memorial Hall."""
    html = await fetch_page(session, "/about/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "About the Memorial Hall",
        "url": f"{BASE_URL}/about/index.html",
        "inscription": None,
        "basic_information": {},
        "timeline": []
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Extract inscription
        inscription_match = re.search(r"Inscription\s*\n([^\n]+(?:\n[^\n]+)*?)\s*Hiroshima National Peace Memorial Hall", text)
        if inscription_match:
            result["inscription"] = clean_text(inscription_match.group(1))
        
        # Extract basic information
        basic_info = {}
        
        # Purpose
        purpose_match = re.search(r"Basic Information\s*\n([^\n]+(?:\n[^\n]+)*?)(?=Founder|$)", text, re.DOTALL)
        if purpose_match:
            basic_info["purpose"] = clean_text(purpose_match.group(1))
        
        # Founder
        founder_match = re.search(r"Founder\s*\n([^\n]+)", text)
        if founder_match:
            basic_info["founder"] = founder_match.group(1).strip()
        
        # Management
        management_match = re.search(r"Management and Operation\s*\n([^\n]+)", text)
        if management_match:
            basic_info["management"] = management_match.group(1).strip()
        
        # Building Details
        building_match = re.search(r"Building Details\s*\n([^\n]+)", text)
        if building_match:
            basic_info["building"] = building_match.group(1).strip()
        
        # Architect
        architect_match = re.search(r"Architect\s*\n([^\n]+)", text)
        if architect_match:
            basic_info["architect"] = architect_match.group(1).strip()
        
        # Opening Day
        opening_match = re.search(r"Opening Day\s*\n([^\n]+)", text)
        if opening_match:
            basic_info["opening_day"] = opening_match.group(1).strip()
        
        result["basic_information"] = basic_info
        
        # Extract timeline
        timeline = []
        timeline_events = re.findall(r'(\d{4})\s*(?:([A-Za-z]+)\s*)?\n([^\n]+)', text)
        for year, month, event in timeline_events:
            if "Atomic Bomb Survivors" in event or "Memorial Hall" in event or "atomic" in event.lower():
                timeline.append({
                    "year": year,
                    "month": month.strip() if month else None,
                    "event": event.strip()
                })
        
        # Key timeline entries
        key_events = {
            "1985": "MHLW conducts first survey of deceased victims",
            "1994": "Establishment of Atomic Bomb Survivors' Assistance Act",
            "1999": "Construction begins on Memorial Hall",
            "2002": "Hiroshima National Peace Memorial Hall opens (August)",
            "2003": "Nagasaki National Peace Memorial Hall opens (July)"
        }
        for year, event in key_events.items():
            timeline.append({"year": year, "event": event})
        
        result["timeline"] = timeline[:10]  # Limit to first 10 entries
    
    return result


async def get_faq(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get FAQ information."""
    html = await fetch_page(session, "/qa/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "FAQ",
        "url": f"{BASE_URL}/qa/index.html",
        "categories": {}
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Parse FAQ categories and Q&A pairs
        categories = {
            "about_facility": {
                "name": "About the Memorial Hall",
                "questions": []
            },
            "facilities": {
                "name": "Facilities",
                "questions": []
            },
            "accessibility": {
                "name": "Accessibility",
                "questions": []
            },
            "victim_registration": {
                "name": "Victim Registration",
                "questions": []
            },
            "memoirs": {
                "name": "Atomic Bomb Memoirs",
                "questions": []
            }
        }
        
        # Extract key FAQ items
        if "What kind of facility" in text:
            categories["about_facility"]["questions"].append({
                "question": "What kind of facility is the Memorial Hall?",
                "answer": "Built by the national government to keep records of victims, pray for world peace, deepen understanding of atomic bombing horrors, and pass down survivor memoirs to future generations."
            })
        
        if "difference between" in text.lower() and "Peace Memorial Museum" in text:
            categories["about_facility"]["questions"].append({
                "question": "What's the difference between the Peace Memorial Museum and the Memorial Hall?",
                "answer": "Peace Memorial Museum uses materials (bombing artifacts, victim possessions) to convey realities. Memorial Hall uses thoughts and words of victims (diaries, memoirs) to convey realities and necessity of peace."
            })
        
        if "Admission is free" in text:
            categories["facilities"]["questions"].append({
                "question": "How much is admission?",
                "answer": "Admission is free."
            })
        
        if "coin-operated lockers" in text.lower():
            categories["facilities"]["questions"].append({
                "question": "Are coin-operated lockers available?",
                "answer": "Yes, 12 lockers on Upper Level. Small (8): W346mm x D422mm x H370mm. Large (4): W346mm x D482mm x H774mm. 100 yen deposit returned after use."
            })
        
        if "wheelchair" in text.lower():
            categories["accessibility"]["questions"].append({
                "question": "Are wheelchairs available?",
                "answer": "Yes, 3 wheelchairs available free of charge at General Information Desk (Upper Level)."
            })
        
        if "assistance dogs" in text.lower() or "seeing-eye dogs" in text.lower():
            categories["accessibility"]["questions"].append({
                "question": "Are assistance dogs allowed?",
                "answer": "Yes, assistance dogs (seeing-eye dogs, helper dogs, hearing-assistance dogs) are allowed inside."
            })
        
        if "eligible for registration" in text.lower():
            categories["victim_registration"]["questions"].append({
                "question": "Which victims are eligible for registration?",
                "answer": "Those directly exposed in Hiroshima/Nagasaki on Aug 6/9, 1945; those who entered within 2 weeks; those affected by rescue efforts; those in utero of women in these categories. Date of death irrelevant; certificate not necessary."
            })
        
        result["categories"] = categories
    
    return result


async def get_notices(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get notices and announcements."""
    html = await fetch_page(session, "/announcement/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "Notices",
        "url": f"{BASE_URL}/announcement/index.html",
        "notices": []
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Parse notices (date + title pattern)
        notice_items = re.findall(r'(\d{4}/\d{2}/\d{2})\s*\n([^\n]+)', text)
        for date, title in notice_items:
            result["notices"].append({
                "date": date,
                "title": title.strip()
            })
    
    return result


async def get_projects(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get main projects and initiatives."""
    html = await fetch_page(session, "/project/index.html")
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup.find('div', {'id': 'main'})
    
    result = {
        "title": "Main Projects and Initiatives",
        "url": f"{BASE_URL}/project/index.html",
        "projects": []
    }
    
    if main:
        text = main.get_text(separator='\n', strip=True)
        
        # Extract project names
        projects = [
            "Registering Victims of the Atomic Bomb",
            "Atomic Bomb Memoirs",
            "Special Exhibitions",
            "Atomic Bomb Memoir Readings",
            "Survivor Testimony Videos",
            "Translation of Testimony Videos and Atomic Bomb Memoirs",
            "Short Film Introduction to the Memorial Hall"
        ]
        
        for project in projects:
            if project in text:
                result["projects"].append({"name": project})
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute skill functions for Hiroshima National Peace Memorial Hall.
    
    Available functions:
    - get_homepage: Get homepage with opening hours, notices, and features
    - get_visitor_info: Get visiting information (hours, admission, directions, facilities)
    - get_floor_guide: Get floor-by-floor facility guide
    - get_about_info: Get information about the Memorial Hall
    - get_faq: Get frequently asked questions
    - get_notices: Get notices and announcements
    - get_projects: Get main projects and initiatives
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == "get_homepage":
                return await get_homepage(session)
            elif function == "get_visitor_info":
                return await get_visitor_info(session)
            elif function == "get_floor_guide":
                return await get_floor_guide(session)
            elif function == "get_about_info":
                return await get_about_info(session)
            elif function == "get_faq":
                return await get_faq(session)
            elif function == "get_notices":
                return await get_notices(session)
            elif function == "get_projects":
                return await get_projects(session)
            else:
                return {"error": f"Unknown function: {function}"}
        except aiohttp.ClientError as e:
            return {"error": f"HTTP error: {str(e)}"}
        except Exception as e:
            return {"error": f"Error: {str(e)}"}


# For testing
if __name__ == "__main__":
    async def test():
        
        print("="*60)
        print("Testing get_homepage")
        print("="*60)
        result = await execute({"function": "get_homepage"})
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_visitor_info")
        print("="*60)
        result = await execute({"function": "get_visitor_info"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_floor_guide")
        print("="*60)
        result = await execute({"function": "get_floor_guide"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_about_info")
        print("="*60)
        result = await execute({"function": "get_about_info"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_faq")
        print("="*60)
        result = await execute({"function": "get_faq"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_notices")
        print("="*60)
        result = await execute({"function": "get_notices"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "="*60)
        print("Testing get_projects")
        print("="*60)
        result = await execute({"function": "get_projects"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())