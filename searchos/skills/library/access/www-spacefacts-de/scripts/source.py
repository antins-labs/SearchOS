"""
SpaceFacts Data Extractor - SearchOS Access Skill

Extracts structured tabular data from www.spacefacts.de including:
- ISS commanders and their mission details
- Astronauts/cosmonauts sorted by time in space
- Active astronauts and cosmonauts
- Astronauts/cosmonauts by first mission date
- Deceased astronauts and cosmonauts
- International space travelers
- Taikonauts (Chinese astronauts)
- Spacecraft relocations
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Any, Optional
import re


BASE_URL = "http://www.spacefacts.de/english/"

# Known data pages with their categories
DATA_PAGES = {
    "iss_commanders": "e_iss-cdr.htm",
    "time_in_space": "e_tis.htm",
    "active_astronauts": "e_active.htm",
    "by_first_mission": "e_first.htm",
    "deceased": "e_death.htm",
    "international": "e_inter.htm",
    "taikonauts": "e_taikonaut.htm",
    "relocations": "e_relocations.htm",
    "all_alphabetical": "e_az.htm",
}


async def fetch_page(url: str) -> str:
    """Fetch a page with proper encoding handling"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()
            
    # Try different encodings
    for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    
    # Fallback
    return content.decode('utf-8', errors='replace')


def extract_iss_commanders(soup: BeautifulSoup) -> dict:
    """Extract ISS commanders data"""
    tables = soup.find_all('table')
    
    # Find the data table (the one with most rows containing ISS-* missions)
    data_table = None
    for table in tables:
        rows = table.find_all('tr')
        if len(rows) > 10:
            # Check if it has ISS missions
            for row in rows[:5]:
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    text = cells[1].get_text(strip=True)
                    if text.startswith('ISS-'):
                        data_table = table
                        break
            if data_table:
                break
    
    if not data_table:
        return {"commanders": [], "error": "Data table not found"}
    
    rows = data_table.find_all('tr')
    commanders = []
    
    for row in rows:
        cells = row.find_all(['th', 'td'])
        if len(cells) >= 5:
            mission = cells[1].get_text(strip=True)
            
            if mission.startswith('ISS-'):
                dates = cells[2].get_text(strip=True)
                duration = cells[3].get_text(strip=True)
                name = cells[4].get_text(strip=True)
                
                # Parse dates
                date_parts = dates.split(' - ')
                start_date = date_parts[0] if len(date_parts) > 0 else ""
                end_date = date_parts[1] if len(date_parts) > 1 else ""
                
                commanders.append({
                    "mission": mission,
                    "commander": name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "duration": duration,
                })
    
    return {
        "commanders": commanders,
        "count": len(commanders),
        "title": "ISS Commanders"
    }


def extract_time_in_space(soup: BeautifulSoup, limit: Optional[int] = None) -> dict:
    """Extract astronauts sorted by time in space"""
    tables = soup.find_all('table')
    
    # Find the data table (largest one)
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    rows = data_table.find_all('tr')
    
    astronauts = []
    
    for i, row in enumerate(rows):
        if i < 2:  # Skip header rows
            continue
            
        cells = row.find_all(['th', 'td'])
        
        if len(cells) >= 14:
            surname = cells[0].get_text(strip=True)
            given_names = cells[1].get_text(strip=True)
            nation = cells[2].get_text(strip=True)
            flights = cells[3].get_text(strip=True)
            
            # Extract flight missions (cells 4-10)
            missions = []
            for j in range(4, 11):
                mission = cells[j].get_text(strip=True)
                if mission:
                    missions.append(mission)
            
            # Time in space (days, hours, minutes)
            days = cells[11].get_text(strip=True)
            hours = cells[12].get_text(strip=True)
            minutes = cells[13].get_text(strip=True)
            status = cells[14].get_text(strip=True) if len(cells) > 14 else ""
            
            # Calculate total time
            try:
                total_days = int(days) if days else 0
                total_hours = int(hours) if hours else 0
                total_minutes = int(minutes) if minutes else 0
                
                # Convert to total hours for sorting
                total_time_hours = total_days * 24 + total_hours + total_minutes / 60
            except:
                total_time_hours = 0
            
            astronauts.append({
                "name": f"{given_names} {surname}",
                "surname": surname,
                "given_names": given_names,
                "nation": nation,
                "flights": int(flights) if flights.isdigit() else flights,
                "missions": missions,
                "time_in_space": {
                    "days": days,
                    "hours": hours,
                    "minutes": minutes,
                    "total_days": days,
                },
                "status": status,
                "_sort_hours": total_time_hours,
            })
    
    # Sort by time in space (already sorted in the page)
    astronauts.sort(key=lambda x: x.get('_sort_hours', 0), reverse=True)
    
    # Remove internal sort field
    for astro in astronauts:
        del astro['_sort_hours']
    
    # Apply limit
    if limit:
        astronauts = astronauts[:limit]
    
    return {
        "astronauts": astronauts,
        "count": len(astronauts),
        "title": "Astronauts/Cosmonauts by Time in Space"
    }


def extract_active_astronauts(soup: BeautifulSoup, limit: Optional[int] = None) -> dict:
    """Extract active astronauts and cosmonauts"""
    tables = soup.find_all('table')
    
    # Find the data table (largest one)
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    rows = data_table.find_all('tr')
    
    astronauts = []
    current_nation = None
    
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        
        if len(cells) == 0:
            continue
        
        # Check for nation header (colspan=11 or similar)
        first_cell = cells[0]
        colspan = first_cell.get('colspan')
        
        if colspan and len(cells) == 1:
            current_nation = first_cell.get_text(strip=True)
            continue
        
        # Skip header row
        if i == 0 or first_cell.get_text(strip=True) == 'Surname':
            continue
        
        if len(cells) >= 5:
            surname = cells[0].get_text(strip=True)
            given_names = cells[1].get_text(strip=True)
            nation = cells[2].get_text(strip=True) if cells[2].get_text(strip=True) else current_nation
            selection = cells[3].get_text(strip=True)
            
            # Extract flights
            flights = []
            for j in range(4, min(len(cells), 12)):
                flight = cells[j].get_text(strip=True)
                if flight:
                    flights.append(flight)
            
            astronauts.append({
                "name": f"{given_names} {surname}",
                "surname": surname,
                "given_names": given_names,
                "nation": nation,
                "selection_date": selection,
                "flights": flights,
            })
    
    if limit:
        astronauts = astronauts[:limit]
    
    return {
        "astronauts": astronauts,
        "count": len(astronauts),
        "title": "Active Astronauts and Cosmonauts"
    }


def extract_by_first_mission(soup: BeautifulSoup, limit: Optional[int] = None) -> dict:
    """Extract astronauts sorted by first mission date"""
    tables = soup.find_all('table')
    
    # Find the data table (largest one)
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    rows = data_table.find_all('tr')
    
    astronauts = []
    
    for i, row in enumerate(rows):
        if i < 2:  # Skip header rows
            continue
            
        cells = row.find_all(['th', 'td'])
        
        if len(cells) >= 6:
            number = cells[0].get_text(strip=True)
            surname = cells[1].get_text(strip=True)
            given_names = cells[2].get_text(strip=True)
            first_mission = cells[3].get_text(strip=True)
            nation = cells[4].get_text(strip=True)
            flights_count = cells[5].get_text(strip=True)
            
            # Extract missions
            missions = []
            for j in range(6, min(len(cells), 15)):
                mission = cells[j].get_text(strip=True)
                if mission:
                    missions.append(mission)
            
            astronauts.append({
                "rank": number,
                "name": f"{given_names} {surname}",
                "surname": surname,
                "given_names": given_names,
                "first_mission_date": first_mission,
                "nation": nation,
                "flights_count": flights_count,
                "missions": missions,
            })
    
    if limit:
        astronauts = astronauts[:limit]
    
    return {
        "astronauts": astronauts,
        "count": len(astronauts),
        "title": "Astronauts/Cosmonauts by First Mission Date"
    }


def extract_deceased(soup: BeautifulSoup, limit: Optional[int] = None) -> dict:
    """Extract deceased astronauts and cosmonauts"""
    tables = soup.find_all('table')
    
    # Find the data table (largest one)
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    rows = data_table.find_all('tr')
    
    astronauts = []
    
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        
        # Skip header row
        if i == 0 or (cells and cells[0].get_text(strip=True) in ['Surname', '']):
            continue
        
        if len(cells) >= 4:
            surname = cells[0].get_text(strip=True)
            given_names = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            nation = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            
            # Look for date information
            death_info = ""
            for j in range(3, len(cells)):
                text = cells[j].get_text(strip=True)
                if text:
                    death_info = text
                    break
            
            astronauts.append({
                "name": f"{given_names} {surname}" if given_names else surname,
                "surname": surname,
                "given_names": given_names,
                "nation": nation,
                "info": death_info,
            })
    
    if limit:
        astronauts = astronauts[:limit]
    
    return {
        "astronauts": astronauts,
        "count": len(astronauts),
        "title": "Deceased Astronauts and Cosmonauts"
    }


def extract_generic_table(soup: BeautifulSoup, title: str, limit: Optional[int] = None) -> dict:
    """Generic table extractor for other pages"""
    tables = soup.find_all('table')
    
    # Find the data table (largest one)
    data_table = max(tables, key=lambda t: len(t.find_all('tr')))
    rows = data_table.find_all('tr')
    
    records = []
    headers = []
    
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        
        if i == 0:
            # Extract headers
            headers = [c.get_text(strip=True) for c in cells]
            continue
        
        # Skip empty rows or header-like rows
        if not cells or (len(cells) == 1 and cells[0].get('colspan')):
            continue
        
        record = {}
        for j, cell in enumerate(cells):
            header = headers[j] if j < len(headers) else f"col_{j}"
            record[header] = cell.get_text(strip=True)
        
        if any(record.values()):  # Only add if at least one field has data
            records.append(record)
    
    if limit:
        records = records[:limit]
    
    return {
        "records": records,
        "count": len(records),
        "title": title,
        "headers": headers,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute SpaceFacts data extraction
    
    Available functions:
    - get_iss_commanders: Get all ISS commanders
    - get_time_in_space: Get astronauts sorted by time in space
    - get_active_astronauts: Get active astronauts/cosmonauts
    - get_by_first_mission: Get astronauts sorted by first mission date
    - get_deceased: Get deceased astronauts/cosmonauts
    - get_international: Get international space travelers
    - get_taikonauts: Get Chinese astronauts
    - get_relocations: Get spacecraft relocations
    - get_all_alphabetical: Get all astronauts alphabetically
    - list_available_pages: List all available data pages
    """
    function = params.get("function", "")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    # Helper to get optional limit
    limit = params.get("limit")
    if limit:
        try:
            limit = int(limit)
        except:
            limit = None
    
    try:
        if function == "list_available_pages":
            return {
                "pages": [
                    {"id": k, "description": v.replace("e_", "").replace(".htm", "").replace("_", " ").title()}
                    for k, v in DATA_PAGES.items()
                ],
                "title": "Available Data Pages"
            }
        
        if function == "get_iss_commanders":
            url = BASE_URL + DATA_PAGES["iss_commanders"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_iss_commanders(soup)
        
        if function == "get_time_in_space":
            url = BASE_URL + DATA_PAGES["time_in_space"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_time_in_space(soup, limit)
        
        if function == "get_active_astronauts":
            url = BASE_URL + DATA_PAGES["active_astronauts"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_active_astronauts(soup, limit)
        
        if function == "get_by_first_mission":
            url = BASE_URL + DATA_PAGES["by_first_mission"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_by_first_mission(soup, limit)
        
        if function == "get_deceased":
            url = BASE_URL + DATA_PAGES["deceased"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_deceased(soup, limit)
        
        if function == "get_international":
            url = BASE_URL + DATA_PAGES["international"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_generic_table(soup, "International Space Travelers", limit)
        
        if function == "get_taikonauts":
            url = BASE_URL + DATA_PAGES["taikonauts"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_generic_table(soup, "Taikonauts (Chinese Astronauts)", limit)
        
        if function == "get_relocations":
            url = BASE_URL + DATA_PAGES["relocations"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_generic_table(soup, "Spacecraft Relocations", limit)
        
        if function == "get_all_alphabetical":
            url = BASE_URL + DATA_PAGES["all_alphabetical"]
            html = await fetch_page(url)
            soup = BeautifulSoup(html, 'html.parser')
            return extract_generic_table(soup, "All Astronauts/Cosmonauts (Alphabetical)", limit)
        
        return {"error": f"Unknown function: {function}"}
        
    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}"}