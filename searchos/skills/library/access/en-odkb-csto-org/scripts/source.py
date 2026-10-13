"""
CSTO (Collective Security Treaty Organization) Access Skill

Fetches structured information from en.odkb-csto.org including:
- 25-year history timeline and organizational structure
- Session summaries and meetings
- News articles
- Documents
- Leadership information
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


BASE_URL = "https://en.odkb-csto.org"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


async def fetch_page(session: aiohttp.ClientSession, path: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch a page and return (html, error) tuple."""
    url = f"{BASE_URL}{path}"
    try:
        async with session.get(url, headers=HEADERS, timeout=30, ssl=False) as response:
            if response.status == 200:
                html = await response.text()
                return html, None
            else:
                return None, f"HTTP {response.status}"
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


def parse_date(date_str: str) -> dict:
    """Parse date string into structured format."""
    # Try DD.MM.YYYY format
    match = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return {
            "day": int(day),
            "month": int(month),
            "year": int(year),
            "formatted": f"{year}-{month}-{day}"
        }
    return {"raw": date_str}


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def get_history(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve the 25-year history timeline and organizational information.
    """
    html, error = await fetch_page(session, "/25years/")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    result = {
        "success": True,
        "title": "From the Treaty to the Organization",
        "url": f"{BASE_URL}/25years/",
        "history": {},
        "organizational_bodies": [],
        "member_states": [],
        "timeline_years": []
    }
    
    # Extract paragraphs for history
    paragraphs = content.find_all('p')
    history_text = []
    for p in paragraphs[:15]:
        text = clean_text(p.get_text())
        if text and len(text) > 50:
            history_text.append(text)
    
    result["history"]["overview"] = history_text
    
    # Extract timeline years from text
    full_text = content.get_text()
    years = sorted(set(re.findall(r'\b(19\d{2}|20\d{2})\b', full_text)))
    result["timeline_years"] = years
    
    # Extract member states from country links
    country_links = content.find_all('a', href=re.compile(r'^/countries/'))
    countries = set()
    for link in country_links:
        href = link.get('href', '')
        match = re.match(r'/countries/([^/]+)/', href)
        if match:
            country_name = match.group(1).replace('_', ' ').title()
            countries.add(country_name)
    result["member_states"] = sorted(list(countries))
    
    # Extract organizational bodies mentioned
    bodies_patterns = [
        ("Collective Security Council", "CSC"),
        ("Council of Foreign Ministers", "CFM"),
        ("Council of Ministers of Defense", "CMD"),
        ("Committee of Secretaries of Security Councils", "CSSC"),
        ("Permanent Council", None),
        ("Secretariat", None),
        ("Joint Staff", None),
        ("Parliamentary Assembly", None)
    ]
    
    for body_name, abbr in bodies_patterns:
        if body_name in full_text:
            body_entry = {"name": body_name}
            if abbr:
                body_entry["abbreviation"] = abbr
            result["organizational_bodies"].append(body_entry)
    
    return result


async def get_sessions(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve list of CSTO sessions with dates and summaries.
    Optional params:
        - year: Filter by specific year (e.g., "2022")
        - limit: Maximum number of sessions to return (default: 20)
    """
    html, error = await fetch_page(session, "/session/")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    year_filter = params.get("year")
    limit = int(params.get("limit", 20))
    
    result = {
        "success": True,
        "title": "CSTO Sessions",
        "url": f"{BASE_URL}/session/",
        "sessions": []
    }
    
    # Find all session links
    links = content.find_all('a', href=True)
    session_links = []
    
    for link in links:
        href = link.get('href', '')
        if '/session/' in href and href != '/session/':
            # Get the text which contains date and description
            text = clean_text(link.get_text())
            if text and len(text) > 10:
                session_links.append({
                    "url": href if href.startswith('http') else f"{BASE_URL}{href}",
                    "text": text
                })
    
    # Parse sessions
    seen_urls = set()
    for item in session_links:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        
        # Extract date from beginning of text (DD.MM.YYYY format)
        date_match = re.match(r'(\d{2}\.\d{2}\.\d{4})', item["text"])
        if date_match:
            date_str = date_match.group(1)
            date_info = parse_date(date_str)
            description = item["text"][10:].strip()  # Remove date prefix
            
            # Apply year filter
            if year_filter and date_info.get("year") != int(year_filter):
                continue
            
            session_entry = {
                "date": date_info,
                "title": description[:200] if description else "Session",
                "url": item["url"]
            }
            result["sessions"].append(session_entry)
            
            if len(result["sessions"]) >= limit:
                break
    
    result["total_count"] = len(result["sessions"])
    return result


async def get_session_detail(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve details of a specific session.
    Required params:
        - url: URL path of the session (e.g., "/session/2022/...")
    """
    url_path = params.get("url")
    if not url_path:
        return {"error": "Missing required parameter: url", "success": False}
    
    # Ensure it starts with /
    if not url_path.startswith('/'):
        url_path = '/' + url_path
    
    html, error = await fetch_page(session, url_path)
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    result = {
        "success": True,
        "url": f"{BASE_URL}{url_path}",
        "date": None,
        "title": None,
        "content": []
    }
    
    # Extract all text content
    text = content.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Find the session date by looking for a date in the URL path or content
    # URLs typically contain the year, e.g., /session/2022/...
    url_year_match = re.search(r'/session/(\d{4})/', url_path)
    url_year = url_year_match.group(1) if url_year_match else None
    
    # Look for the session date - it's usually a standalone date line followed by content
    session_date = None
    session_title = None
    content_start_idx = 0
    
    for i, line in enumerate(lines):
        # Skip "All News" and similar navigation
        if line.lower() in ['all news', 'news', 'sessions']:
            continue
        
        # Check for date format DD.MM.YYYY
        date_match = re.match(r'^(\d{2}\.\d{2}\.\d{4})$', line)
        if date_match:
            date_str = date_match.group(1)
            parsed_date = parse_date(date_str)
            
            # If this date matches the URL year, it's likely the session date
            if url_year and parsed_date.get("year") == int(url_year):
                session_date = parsed_date
                # The next substantial line is the title
                for j in range(i + 1, min(i + 5, len(lines))):
                    if len(lines[j]) > 50 and not re.match(r'^\d{2}\.\d{2}\.\d{4}$', lines[j]):
                        session_title = lines[j][:300]
                        content_start_idx = j + 1
                        break
                break
            elif not url_year and not session_date:
                # Use the first date found if no URL year
                session_date = parsed_date
                for j in range(i + 1, min(i + 5, len(lines))):
                    if len(lines[j]) > 50 and not re.match(r'^\d{2}\.\d{2}\.\d{4}$', lines[j]):
                        session_title = lines[j][:300]
                        content_start_idx = j + 1
                        break
                break
    
    result["date"] = session_date
    result["title"] = session_title
    
    # Extract main content - all text after the title until we hit "Go back" or similar
    for i in range(content_start_idx, len(lines)):
        line = lines[i]
        
        # Stop at navigation elements
        if line.lower() in ['go back', 'back to the section', 'back to the all news']:
            break
        
        # Stop at standalone dates (news items)
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', line):
            # Check if this is a news item (has a year different from session)
            parsed = parse_date(line)
            if session_date and parsed.get("year") != session_date.get("year"):
                break
        
        # Add substantive content
        if len(line) > 20:
            result["content"].append(line)
    
    return result


async def get_news(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve recent CSTO news.
    Optional params:
        - limit: Maximum number of news items to return (default: 15)
    """
    html, error = await fetch_page(session, "/news/")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    limit = int(params.get("limit", 15))
    
    result = {
        "success": True,
        "title": "CSTO News",
        "url": f"{BASE_URL}/news/",
        "news": []
    }
    
    # Find all news links
    links = content.find_all('a', href=True)
    news_links = []
    
    for link in links:
        href = link.get('href', '')
        if '/news/' in href and href != '/news/':
            text = clean_text(link.get_text())
            if text and len(text) > 10:
                news_links.append({
                    "url": href if href.startswith('http') else f"{BASE_URL}{href}",
                    "text": text
                })
    
    # Parse news items
    seen_urls = set()
    for item in news_links:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        
        # Extract date
        date_match = re.match(r'(\d{2}\.\d{2}\.\d{4})', item["text"])
        if date_match:
            date_str = date_match.group(1)
            date_info = parse_date(date_str)
            title = item["text"][10:].strip()
            
            news_entry = {
                "date": date_info,
                "title": title[:200] if title else "News",
                "url": item["url"]
            }
            result["news"].append(news_entry)
            
            if len(result["news"]) >= limit:
                break
    
    result["total_count"] = len(result["news"])
    return result


async def get_documents(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve CSTO documents and treaties.
    Optional params:
        - limit: Maximum number of documents to return (default: 20)
    """
    html, error = await fetch_page(session, "/documents/")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    limit = int(params.get("limit", 20))
    
    result = {
        "success": True,
        "title": "CSTO Documents",
        "url": f"{BASE_URL}/documents/",
        "documents": []
    }
    
    # Find all document links
    links = content.find_all('a', href=True)
    doc_links = []
    
    for link in links:
        href = link.get('href', '')
        text = clean_text(link.get_text())
        if text and len(text) > 10 and '/documents/' in href:
            doc_links.append({
                "url": href if href.startswith('http') else f"{BASE_URL}{href}",
                "text": text
            })
    
    # Parse documents
    seen_urls = set()
    for item in doc_links:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        
        # Extract date
        date_match = re.match(r'(\d{2}\.\d{2}\.\d{4})', item["text"])
        date_info = parse_date(date_match.group(1)) if date_match else None
        title = item["text"][10:].strip() if date_match else item["text"]
        
        doc_entry = {
            "title": title[:300] if title else "Document",
            "url": item["url"]
        }
        if date_info:
            doc_entry["date"] = date_info
        
        result["documents"].append(doc_entry)
        
        if len(result["documents"]) >= limit:
            break
    
    result["total_count"] = len(result["documents"])
    return result


async def get_leadership(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve leadership history (Secretaries General and Deputies).
    """
    html, error = await fetch_page(session, "/25years/istoriya-rukovodstva")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    result = {
        "success": True,
        "title": "CSTO Leadership History",
        "url": f"{BASE_URL}/25years/istoriya-rukovodstva",
        "secretaries_general": [],
        "deputy_secretaries_general": []
    }
    
    text = content.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    current_section = None
    current_person = None
    
    for line in lines:
        if "General Secretaries" in line:
            current_section = "secretaries_general"
            continue
        elif "Deputy General Secretaries" in line:
            current_section = "deputy_secretaries_general"
            continue
        
        if not current_section:
            continue
        
        # Skip navigation items
        if any(nav in line for nav in ["From the Treaty", "News", "Leadership", "Photo", "Video"]):
            continue
        
        # Check if this is a person name (contains name-like pattern)
        if re.match(r'^[A-Z][a-z]+\s+[A-Z]', line) and len(line) < 60:
            current_person = {"name": line}
        elif current_person and ("19" in line or "20" in line or "present" in line.lower()):
            # This is a date/period line
            current_person["period"] = line
            if current_section == "secretaries_general":
                result["secretaries_general"].append(current_person)
            else:
                result["deputy_secretaries_general"].append(current_person)
            current_person = None
    
    return result


async def get_structure(params: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
    """
    Retrieve CSTO organizational structure.
    """
    html, error = await fetch_page(session, "/structure/")
    if error:
        return {"error": error, "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('#content')
    
    if not content:
        return {"error": "Content not found", "success": False}
    
    result = {
        "success": True,
        "title": "CSTO Structure",
        "url": f"{BASE_URL}/structure/",
        "bodies": []
    }
    
    text = content.get_text(separator='\n', strip=True)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Extract organizational bodies
    known_bodies = [
        "Collective Security Council",
        "Permanent Council",
        "Secretary General",
        "Secretariat",
        "Joint Staff",
        "Parliamentary Assembly",
        "Council of Ministers of Foreign Affairs",
        "Council of Ministers of Defense",
        "Committee of Secretaries of the Security Council",
        "Afghanistan Working Group",
        "Military Committee",
        "Working Group on Information Policy",
        "Working Group on Coordination",
        "Working Group on Combating Terrorism"
    ]
    
    for line in lines:
        for body in known_bodies:
            if body.lower() in line.lower():
                if body not in [b["name"] for b in result["bodies"]]:
                    result["bodies"].append({"name": body})
                break
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the CSTO access skill.
    
    Dispatches based on params["function"]:
        - get_history: Get 25-year history and organizational overview
        - get_sessions: Get list of sessions (optional: year, limit)
        - get_session_detail: Get details of a specific session (requires: url)
        - get_news: Get recent news (optional: limit)
        - get_documents: Get documents list (optional: limit)
        - get_leadership: Get leadership history
        - get_structure: Get organizational structure
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "success": False,
            "available_functions": [
                "get_history",
                "get_sessions",
                "get_session_detail",
                "get_news",
                "get_documents",
                "get_leadership",
                "get_structure"
            ]
        }
    
    async with aiohttp.ClientSession() as session:
        if function == "get_history":
            return await get_history(params, session)
        elif function == "get_sessions":
            return await get_sessions(params, session)
        elif function == "get_session_detail":
            return await get_session_detail(params, session)
        elif function == "get_news":
            return await get_news(params, session)
        elif function == "get_documents":
            return await get_documents(params, session)
        elif function == "get_leadership":
            return await get_leadership(params, session)
        elif function == "get_structure":
            return await get_structure(params, session)
        else:
            return {
                "error": f"Unknown function: {function}",
                "success": False,
                "available_functions": [
                    "get_history",
                    "get_sessions",
                    "get_session_detail",
                    "get_news",
                    "get_documents",
                    "get_leadership",
                    "get_structure"
                ]
            }