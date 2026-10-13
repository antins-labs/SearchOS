"""
KOF Wiki (kof.fandom.com) Access Skill

Retrieves structured information about King of Fighters characters, bosses,
teams, and games from the KOF Wiki using the MediaWiki API.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import quote


API_BASE = "https://kof.fandom.com/api.php"
HEADERS = {
    "User-Agent": "SearchOS-KOF-Skill/1.0",
    "Accept": "application/json",
}


async def _api_request(session: aiohttp.ClientSession, params: dict) -> dict:
    """Make a MediaWiki API request."""
    params["format"] = "json"
    try:
        async with session.get(API_BASE, params=params, headers=HEADERS, timeout=30) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"error": {"code": "http_error", "info": f"HTTP {resp.status}"}}
    except asyncio.TimeoutError:
        return {"error": {"code": "timeout", "info": "Request timed out"}}
    except Exception as e:
        return {"error": {"code": "exception", "info": str(e)}}


async def _get_page_content(session: aiohttp.ClientSession, page_title: str) -> dict:
    """Fetch a wiki page's content and metadata."""
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text|categories|sections|links",
        "redirects": "true",
        "disablelimitreport": "true",
    }
    return await _api_request(session, params)


async def _get_category_members(session: aiohttp.ClientSession, category: str, limit: int = 100) -> list:
    """Get all members of a category with pagination."""
    all_members = []
    cmcontinue = None
    
    while len(all_members) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": min(50, limit - len(all_members)),
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        
        data = await _api_request(session, params)
        if "error" in data:
            break
        
        query = data.get("query", {})
        members = query.get("categorymembers", [])
        all_members.extend(members)
        
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    
    return all_members[:limit]


async def _search_pages(session: aiohttp.ClientSession, query: str, limit: int = 20) -> list:
    """Search for wiki pages."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srprop": "snippet|titlesnippet|wordcount",
    }
    data = await _api_request(session, params)
    return data.get("query", {}).get("search", [])


def _extract_bosses_from_html(html: str) -> list:
    """Extract boss information from the Boss page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    bosses = []
    current_saga = None
    
    for heading in soup.find_all(["h2", "h3"]):
        h_text = heading.get_text(strip=True).replace("[]", "")
        
        if not h_text or h_text.lower() == "contents":
            continue
        
        if "Saga" in h_text or "bosses" in h_text.lower():
            current_saga = h_text
        elif heading.name == "h3" and current_saga:
            boss_info = {
                "name": h_text,
                "saga": current_saga,
                "description": None,
                "link": None,
            }
            
            # Get description from next paragraph
            next_p = heading.find_next("p")
            if next_p:
                desc = next_p.get_text(strip=True)
                if desc and len(desc) > 10:
                    boss_info["description"] = desc[:500]
            
            # Get link to full page
            link = heading.find("a")
            if link and link.get("href"):
                boss_info["link"] = f"https://kof.fandom.com{link['href']}"
            
            bosses.append(boss_info)
    
    return bosses


def _extract_character_info(html: str, title: str) -> dict:
    """Extract character information from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    info = {
        "name": title,
        "description": None,
        "sections": [],
        "categories": [],
        "links": [],
        "story": None,
        "personality": None,
        "powers": None,
        "fighting_style": None,
        "game_appearances": [],
    }
    
    # Get first paragraph as description
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 30 and not text.startswith("Redirect"):
            info["description"] = text[:500]
            break
    
    # Extract sections and their content
    for heading in soup.find_all(["h2", "h3", "h4"]):
        h_text = heading.get_text(strip=True).replace("[]", "")
        if h_text and h_text.lower() != "contents":
            info["sections"].append(h_text)
            
            # Extract specific sections
            section_lower = h_text.lower()
            if "story" in section_lower and not info["story"]:
                next_p = heading.find_next("p")
                if next_p:
                    info["story"] = next_p.get_text(strip=True)[:500]
            elif "personality" in section_lower and not info["personality"]:
                next_p = heading.find_next("p")
                if next_p:
                    info["personality"] = next_p.get_text(strip=True)[:500]
            elif "power" in section_lower and not info["powers"]:
                next_p = heading.find_next("p")
                if next_p:
                    info["powers"] = next_p.get_text(strip=True)[:500]
            elif "fighting style" in section_lower and not info["fighting_style"]:
                next_p = heading.find_next("p")
                if next_p:
                    info["fighting_style"] = next_p.get_text(strip=True)[:500]
            elif "appearance" in section_lower and not info["game_appearances"]:
                # Get game appearances
                next_ul = heading.find_next(["ul", "ol"])
                if next_ul:
                    for li in next_ul.find_all("li")[:15]:
                        text = li.get_text(strip=True)
                        if text:
                            info["game_appearances"].append(text)
    
    # Get related wiki links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if "/wiki/" in href and text and len(text) > 2 and ":" not in href:
            if text not in info["links"] and len(info["links"]) < 30:
                info["links"].append(text)
    
    return info


def _extract_team_info(html: str, title: str) -> dict:
    """Extract team information from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    info = {
        "name": title,
        "description": None,
        "members": [],
        "related_characters": [],
        "games": [],
    }
    
    # Get first paragraph as description
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 30 and not text.startswith("Redirect"):
            info["description"] = text[:500]
            break
    
    # Extract character links
    seen_chars = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if "/wiki/" in href and text and len(text) > 2 and ":" not in href:
            if "Team" not in text and text not in seen_chars:
                seen_chars.add(text)
                if len(info["related_characters"]) < 20:
                    info["related_characters"].append(text)
    
    return info


def _format_error(data: dict) -> str:
    """Format error message from API response."""
    error = data.get("error", {})
    if isinstance(error, dict):
        return error.get("info", error.get("code", "Unknown error"))
    return str(error)


async def get_bosses(session: aiohttp.ClientSession, saga: str = None) -> dict:
    """Get list of bosses, optionally filtered by saga."""
    data = await _get_page_content(session, "Boss")
    
    if "error" in data:
        return {"error": _format_error(data), "bosses": []}
    
    parse = data.get("parse", {})
    html = parse.get("text", {}).get("*", "")
    
    bosses = _extract_bosses_from_html(html)
    
    # Filter by saga if specified
    if saga:
        saga_lower = saga.lower()
        bosses = [b for b in bosses if saga_lower in b.get("saga", "").lower()]
    
    return {
        "total": len(bosses),
        "bosses": bosses,
        "source": "https://kof.fandom.com/wiki/Boss",
    }


async def get_character(session: aiohttp.ClientSession, name: str) -> dict:
    """Get detailed information about a character."""
    data = await _get_page_content(session, name)
    
    if "error" in data:
        return {"error": _format_error(data), "character": None}
    
    parse = data.get("parse", {})
    
    if "error" in parse:
        return {"error": _format_error(parse), "character": None}
    
    html = parse.get("text", {}).get("*", "")
    title = parse.get("title", name)
    
    # Check if this is a redirect or empty page
    if not html or len(html) < 100:
        return {"error": f"Page '{name}' has no content or is a redirect", "character": None}
    
    info = _extract_character_info(html, title)
    info["categories"] = [c.get("*") for c in parse.get("categories", [])]
    info["page_id"] = parse.get("pageid")
    info["source"] = f"https://kof.fandom.com/wiki/{quote(title.replace(' ', '_'))}"
    
    return {"character": info}


async def get_characters_list(session: aiohttp.ClientSession, limit: int = 100) -> dict:
    """Get list of all characters."""
    members = await _get_category_members(session, "Characters", limit)
    
    characters = []
    for m in members:
        characters.append({
            "name": m.get("title"),
            "page_id": m.get("pageid"),
            "link": f"https://kof.fandom.com/wiki/{quote(m.get('title', '').replace(' ', '_'))}",
        })
    
    return {
        "total": len(characters),
        "characters": characters,
    }


async def get_teams(session: aiohttp.ClientSession) -> dict:
    """Get list of all teams."""
    members = await _get_category_members(session, "Teams", 100)
    
    teams = []
    for m in members:
        teams.append({
            "name": m.get("title"),
            "page_id": m.get("pageid"),
            "link": f"https://kof.fandom.com/wiki/{quote(m.get('title', '').replace(' ', '_'))}",
        })
    
    return {
        "total": len(teams),
        "teams": teams,
    }


async def get_team(session: aiohttp.ClientSession, name: str) -> dict:
    """Get detailed information about a team."""
    data = await _get_page_content(session, name)
    
    if "error" in data:
        return {"error": _format_error(data), "team": None}
    
    parse = data.get("parse", {})
    
    if "error" in parse:
        return {"error": _format_error(parse), "team": None}
    
    html = parse.get("text", {}).get("*", "")
    title = parse.get("title", name)
    
    if not html or len(html) < 100:
        return {"error": f"Team '{name}' has no content or does not exist", "team": None}
    
    info = _extract_team_info(html, title)
    info["categories"] = [c.get("*") for c in parse.get("categories", [])]
    info["page_id"] = parse.get("pageid")
    info["source"] = f"https://kof.fandom.com/wiki/{quote(title.replace(' ', '_'))}"
    
    return {"team": info}


async def search(session: aiohttp.ClientSession, query: str, limit: int = 20) -> dict:
    """Search the wiki for pages matching a query."""
    results = await _search_pages(session, query, limit)
    
    search_results = []
    for r in results:
        search_results.append({
            "title": r.get("title"),
            "snippet": r.get("snippet", "").replace("<span class='searchmatch'>", "").replace("</span>", ""),
            "word_count": r.get("wordcount"),
            "link": f"https://kof.fandom.com/wiki/{quote(r.get('title', '').replace(' ', '_'))}",
        })
    
    return {
        "query": query,
        "total": len(search_results),
        "results": search_results,
    }


async def get_page(session: aiohttp.ClientSession, title: str) -> dict:
    """Get any wiki page content."""
    data = await _get_page_content(session, title)
    
    if "error" in data:
        return {"error": _format_error(data), "page": None}
    
    parse = data.get("parse", {})
    
    if "error" in parse:
        return {"error": _format_error(parse), "page": None}
    
    html = parse.get("text", {}).get("*", "")
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract text content
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 20:
            paragraphs.append(text)
    
    # Extract headings
    headings = []
    for h in soup.find_all(["h2", "h3", "h4"]):
        h_text = h.get_text(strip=True).replace("[]", "")
        if h_text and h_text.lower() != "contents":
            headings.append(h_text)
    
    # Extract links
    links = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if "/wiki/" in href and text and len(text) > 2 and ":" not in href and text not in seen:
            seen.add(text)
            if len(links) < 50:
                links.append({"text": text, "href": href})
    
    return {
        "page": {
            "title": parse.get("title"),
            "page_id": parse.get("pageid"),
            "categories": [c.get("*") for c in parse.get("categories", [])],
            "sections": [s.get("line") for s in parse.get("sections", [])],
            "headings": headings,
            "content": paragraphs[:20],
            "links": links,
            "source": f"https://kof.fandom.com/wiki/{quote(parse.get('title', '').replace(' ', '_'))}",
        }
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute KOF Wiki skill functions.
    
    Available functions:
    - get_bosses: Get list of bosses (optional 'saga' filter)
    - get_character: Get character details (requires 'name')
    - get_characters: Get list of all characters (optional 'limit')
    - get_teams: Get list of all teams
    - get_team: Get team details (requires 'name')
    - search: Search the wiki (requires 'query', optional 'limit')
    - get_page: Get any wiki page (requires 'title')
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession() as session:
        if function == "get_bosses":
            saga = params.get("saga")
            return await get_bosses(session, saga)
        
        elif function == "get_character":
            name = params.get("name")
            if not name:
                return {"error": "Missing required parameter: name", "character": None}
            return await get_character(session, name)
        
        elif function == "get_characters":
            limit = params.get("limit", 100)
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = 100
            return await get_characters_list(session, limit)
        
        elif function == "get_teams":
            return await get_teams(session)
        
        elif function == "get_team":
            name = params.get("name")
            if not name:
                return {"error": "Missing required parameter: name", "team": None}
            return await get_team(session, name)
        
        elif function == "search":
            query = params.get("query")
            if not query:
                return {"error": "Missing required parameter: query", "results": []}
            limit = params.get("limit", 20)
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                limit = 20
            return await search(session, query, limit)
        
        elif function == "get_page":
            title = params.get("title")
            if not title:
                return {"error": "Missing required parameter: title", "page": None}
            return await get_page(session, title)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_bosses",
                    "get_character",
                    "get_characters",
                    "get_teams",
                    "get_team",
                    "search",
                    "get_page",
                ],
            }