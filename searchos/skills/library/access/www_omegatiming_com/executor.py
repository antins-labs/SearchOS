"""
Omega Timing Live Results Extractor

Fetches live timing results from Omega Timing's official website for
Olympic Games, World Championships, and other major sporting events.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://www.omegatiming.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page and return HTML content."""
    response = await client.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.text


async def fetch_xml(client: httpx.AsyncClient, url: str) -> str:
    """Fetch XML content."""
    xml_headers = {**HEADERS, "Accept": "application/xml,text/xml,*/*"}
    response = await client.get(url, headers=xml_headers)
    response.raise_for_status()
    return response.text


def parse_diving_xml(xml_content: str) -> Dict[str, Any]:
    """Parse diving event XML and return structured data."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {str(e)}", "raw_length": len(xml_content)}
    
    result = {
        "sport": "diving",
        "metadata": {},
        "timetable": [],
        "events": []
    }
    
    # Extract metadata
    for child in root:
        if child.tag not in ["event", "timetable"]:
            result["metadata"][child.tag] = child.text
    
    # Extract timetable
    timetable = root.find("timetable")
    if timetable is not None:
        for event in timetable.findall("event"):
            entry = {"code": event.get("name")}
            for elem in event:
                entry[elem.tag] = elem.text
            result["timetable"].append(entry)
    
    # Extract events with full results
    for event_elem in root.findall("event"):
        event_data = {
            "code": event_elem.get("name"),
            "rsccode": event_elem.findtext("rsccode"),
            "fullname": event_elem.findtext("fullname"),
            "phase": event_elem.findtext("phase"),
            "height": event_elem.findtext("height"),
            "gender": event_elem.findtext("gender"),
            "timestamp": event_elem.findtext("timestamp"),
            "diver_count": event_elem.findtext("divercount"),
            "judges": [],
            "divers": []
        }
        
        # Extract judges
        judges_elem = event_elem.find("judges")
        if judges_elem is not None:
            for judge in judges_elem:
                if judge.tag.startswith("judge"):
                    event_data["judges"].append({
                        "type": judge.tag,
                        "number": judge.get("n"),
                        "name": judge.text
                    })
                elif judge.tag in ["refereea", "refereeb", "assistanta", "assistantb"]:
                    event_data["judges"].append({
                        "type": judge.tag,
                        "name": judge.text
                    })
        
        # Extract divers
        divers_elem = event_elem.find("divers")
        if divers_elem is not None:
            for diver in divers_elem.findall("diver"):
                diver_data = {
                    "id": diver.findtext("id1"),
                    "name": diver.findtext("name1"),
                    "surname": diver.findtext("surname1"),
                    "gender": diver.findtext("gender1"),
                    "born": diver.findtext("born1"),
                    "nation": diver.findtext("nation1"),
                    "score": diver.findtext("score"),
                    "rank": diver.findtext("rank"),
                    "order": diver.findtext("order"),
                    "dives": []
                }
                
                # Extract dive results
                results_elem = diver.find("results")
                if results_elem is not None:
                    for dive in results_elem.findall("dive"):
                        dive_data = {
                            "id": dive.findtext("id"),
                            "height": dive.findtext("h"),
                            "difficulty": dive.findtext("dd"),
                            "points": dive.findtext("points"),
                            "scores": []
                        }
                        
                        scores_elem = dive.find("scores")
                        if scores_elem is not None:
                            for score in scores_elem.findall("j"):
                                dive_data["scores"].append({
                                    "judge": score.get("n"),
                                    "score": score.text
                                })
                        
                        diver_data["dives"].append(dive_data)
                
                event_data["divers"].append(diver_data)
        
        result["events"].append(event_data)
    
    return result


async def get_events_list(client: httpx.AsyncClient, year: Optional[int] = None) -> List[Dict[str, str]]:
    """Get list of events from the results page."""
    url = f"{BASE_URL}/sports-timing-live-results"
    html = await fetch_page(client, url)
    soup = BeautifulSoup(html, 'html.parser')
    
    events = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        # Match year-based event URLs
        match = re.match(r'^/(\d{4})/(.+)-live-results$', href)
        if match:
            event_year = int(match.group(1))
            event_slug = match.group(2)
            
            # Filter by year if specified
            if year is None or event_year == year:
                events.append({
                    "year": event_year,
                    "slug": event_slug,
                    "name": text,
                    "url": f"{BASE_URL}{href}"
                })
    
    return events


async def get_event_files(client: httpx.AsyncClient, event_url: str) -> Dict[str, Any]:
    """Get available files (PDFs and XML) for an event."""
    html = await fetch_page(client, event_url)
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "event_title": soup.title.string if soup.title else "Unknown",
        "url": event_url,
        "files": {
            "pdf": [],
            "xml": [],
            "other": []
        },
        "schedule": [],
        "disciplines": []
    }
    
    # Find page wrapper
    page_wrapper = soup.find('div', class_='page-wrapper')
    if not page_wrapper:
        return result
    
    # Extract files
    for link in page_wrapper.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        
        if href.startswith('/File/'):
            file_data = {
                "url": f"{BASE_URL}{href}",
                "filename": href.split('/')[-1],
                "description": text
            }
            
            if href.endswith('.pdf'):
                result["files"]["pdf"].append(file_data)
            elif href.endswith('.xml'):
                result["files"]["xml"].append(file_data)
            else:
                result["files"]["other"].append(file_data)
    
    # Extract schedule/dates
    for date_row in page_wrapper.find_all('div', class_='row date'):
        date_text = date_row.get_text(strip=True)
        if date_text:
            result["schedule"].append(date_text)
    
    # Extract disciplines from dropdown
    for option in page_wrapper.find_all('option'):
        value = option.get('value', '')
        text = option.get_text(strip=True)
        if value and value != 'all' and text:
            result["disciplines"].append({"value": value, "name": text})
    
    return result


async def get_xml_results(client: httpx.AsyncClient, xml_url: str) -> Dict[str, Any]:
    """Fetch and parse XML results file."""
    xml_content = await fetch_xml(client, xml_url)
    
    # Detect sport type from XML root element
    try:
        root = ET.fromstring(xml_content)
        sport_type = root.tag.lower()
    except ET.ParseError:
        return {"error": "Failed to parse XML", "raw_length": len(xml_content)}
    
    # Parse based on sport type
    if sport_type == "diving":
        return parse_diving_xml(xml_content)
    else:
        # Generic XML parsing
        return {
            "sport": sport_type,
            "raw_xml_length": len(xml_content),
            "metadata": {child.tag: child.text for child in root if child.text and len(child.text) < 1000},
            "note": f"Parsing not implemented for sport type: {sport_type}"
        }


async def search_events(client: httpx.AsyncClient, query: str) -> List[Dict[str, str]]:
    """Search events by name or keyword."""
    events = await get_events_list(client)
    
    query_lower = query.lower()
    results = []
    
    for event in events:
        if query_lower in event['name'].lower() or query_lower in event['slug'].lower():
            results.append(event)
    
    return results


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main execution function.
    
    Args:
        params: Dict containing:
            - function: str - One of 'list_events', 'get_event_files', 'get_xml_results', 'search_events'
            - year: int (optional) - Filter events by year (for list_events)
            - event_url: str - Event page URL (for get_event_files)
            - xml_url: str - XML file URL (for get_xml_results)
            - query: str - Search query (for search_events)
        ctx: Context (unused)
    
    Returns:
        Dict with results or error information
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            if function == "list_events":
                year = params.get("year")
                events = await get_events_list(client, year)
                return {
                    "success": True,
                    "count": len(events),
                    "events": events
                }
            
            elif function == "get_event_files":
                event_url = params.get("event_url")
                if not event_url:
                    return {"error": "Missing required parameter: event_url"}
                
                files = await get_event_files(client, event_url)
                return {
                    "success": True,
                    **files
                }
            
            elif function == "get_xml_results":
                xml_url = params.get("xml_url")
                if not xml_url:
                    return {"error": "Missing required parameter: xml_url"}
                
                results = await get_xml_results(client, xml_url)
                return {
                    "success": True,
                    **results
                }
            
            elif function == "search_events":
                query = params.get("query")
                if not query:
                    return {"error": "Missing required parameter: query"}
                
                results = await search_events(client, query)
                return {
                    "success": True,
                    "query": query,
                    "count": len(results),
                    "results": results
                }
            
            else:
                return {"error": f"Unknown function: {function}"}
        
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {e.response.status_code}", "url": str(e.request.url)}
        except httpx.RequestError as e:
            return {"error": f"Request error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}", "type": type(e).__name__}


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Test list events
            print("=== Testing list_events ===")
            result = await execute({"function": "list_events", "year": 2026})
            print(json.dumps(result, indent=2)[:1000])
            
            if result.get("success") and result.get("events"):
                # Test get_event_files
                print("\n=== Testing get_event_files ===")
                test_event = result["events"][0]["url"]
                result2 = await execute({"function": "get_event_files", "event_url": test_event})
                print(json.dumps(result2, indent=2)[:1000])
                
                # Test get_xml_results if XML available
                if result2.get("files", {}).get("xml"):
                    print("\n=== Testing get_xml_results ===")
                    xml_url = result2["files"]["xml"][0]["url"]
                    result3 = await execute({"function": "get_xml_results", "xml_url": xml_url})
                    print(json.dumps(result3, indent=2)[:2000])
            
            # Test search
            print("\n=== Testing search_events ===")
            result4 = await execute({"function": "search_events", "query": "diving"})
            print(json.dumps(result4, indent=2)[:1000])
    
    asyncio.run(test())