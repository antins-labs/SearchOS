"""
World Athletics Rankings Access Skill

Fetches world rankings data from worldathletics.org including:
- Overall rankings (men/women)
- Event-specific rankings (100m, 1500m, marathon, etc.)
- Supports pagination, region filtering, and age category filtering
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin, urlencode


BASE_URL = "https://worldathletics.org"

# Common event slugs for convenience
EVENT_SLUGS = {
    "overall": "overall-ranking",
    "100m": "100-metres",
    "200m": "200-metres",
    "400m": "400-metres",
    "800m": "800-metres",
    "1500m": "1500-metres",
    "5000m": "5000-metres",
    "10000m": "10000-metres",
    "marathon": "marathon",
    "half-marathon": "half-marathon",
    "110m-hurdles": "110-metres-hurdles",
    "400m-hurdles": "400-metres-hurdles",
    "high-jump": "high-jump",
    "pole-vault": "pole-vault",
    "long-jump": "long-jump",
    "triple-jump": "triple-jump",
    "shot-put": "shot-put",
    "discus": "discus-throw",
    "hammer": "hammer-throw",
    "javelin": "javelin-throw",
    "decathlon": "decathlon",
    "heptathlon": "heptathlon",
    "60m": "60-metres",
    "60m-hurdles": "60-metres-hurdles",
    "3000m": "3000-metres",
    "3000m-steeple": "3000-metres-steeplechase",
    "mile": "one-mile",
    "4x100m": "4x100-metres-relay",
    "4x400m": "4x400-metres-relay",
}

# Region type options
REGION_TYPES = {
    "world": "world",
    "area": "area",
    "country": "countries",
    "country-group": "country-group",
}

# Area codes
AREAS = {
    "africa": "africa",
    "asia": "asia",
    "europe": "europe",
    "north-america": "north and central america",
    "oceania": "oceania",
    "south-america": "south america",
}

# Age categories
AGE_CATEGORIES = {
    "senior": "senior",
    "u20": "u20",
    "u18": "u18",
}


async def fetch_page(
    session: aiohttp.ClientSession,
    event: str,
    gender: str,
    page: int = 1,
    region_type: Optional[str] = None,
    region: Optional[str] = None,
    age_category: Optional[str] = None,
) -> tuple[list[dict], dict]:
    """
    Fetch a single page of rankings.
    
    Returns:
        tuple: (list of athlete rankings, pagination info)
    """
    # Build URL
    event_slug = EVENT_SLUGS.get(event, event)
    url = f"{BASE_URL}/world-rankings/{event_slug}/{gender}"
    
    # Build query parameters
    params = {}
    if page > 1:
        params["page"] = page
    if region_type and region_type != "world":
        params["regionType"] = REGION_TYPES.get(region_type, region_type)
        if region:
            params["region"] = region
    if age_category and age_category != "senior":
        params["ageCategory"] = age_category
    
    if params:
        url = f"{url}?{urlencode(params)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status} for {url}")
        
        content = await resp.text()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Parse the rankings table
        rankings = []
        tables = soup.find_all('table')
        
        if tables:
            tbody = tables[0].find('tbody')
            if tbody:
                trs = tbody.find_all('tr')
                for tr in trs:
                    tds = tr.find_all('td')
                    if len(tds) >= 5:
                        # Extract athlete URL
                        athlete_url = tr.get('data-athlete-url', '')
                        athlete_id = tr.get('data-id', '')
                        
                        # Extract nationality from flag image
                        nat_img = tds[3].find('img') if len(tds) > 3 else None
                        nationality = nat_img.get('alt', '') if nat_img else ''
                        
                        ranking = {
                            "rank": int(tds[0].get_text(strip=True)) if tds[0].get_text(strip=True).isdigit() else tds[0].get_text(strip=True),
                            "athlete": tds[1].get_text(strip=True),
                            "dob": tds[2].get_text(strip=True),
                            "nationality": nationality,
                            "score": int(tds[4].get_text(strip=True)) if tds[4].get_text(strip=True).isdigit() else tds[4].get_text(strip=True),
                            "events": tds[5].get_text(strip=True) if len(tds) > 5 else "",
                            "athlete_url": f"{BASE_URL}{athlete_url}" if athlete_url else None,
                            "athlete_id": athlete_id,
                        }
                        rankings.append(ranking)
        
        # Parse pagination info
        pagination_info = parse_pagination(soup)
        
        return rankings, pagination_info


def parse_pagination(soup: BeautifulSoup) -> dict:
    """Extract pagination information from the page."""
    pagination = soup.find(class_='toplist-pagination')
    if not pagination:
        return {"current_page": 1, "total_pages": 1, "has_next": False, "has_prev": False}
    
    # Find current page
    current_btn = pagination.find('a', class_='pagination--current')
    current_page = 1
    if current_btn:
        try:
            current_page = int(current_btn.get_text(strip=True))
        except ValueError:
            pass
    
    # Find total pages (last numbered button)
    page_buttons = pagination.find_all('a', class_='btn--pagination')
    total_pages = current_page
    for btn in page_buttons:
        text = btn.get_text(strip=True)
        if text.isdigit():
            total_pages = max(total_pages, int(text))
    
    # Check for next/prev buttons
    next_btn = pagination.find('a', string=re.compile(r'^>$|^>>$'))
    prev_btn = pagination.find('a', string=re.compile(r'^<$|^<<$'))
    
    return {
        "current_page": current_page,
        "total_pages": total_pages,
        "has_next": next_btn is not None,
        "has_prev": prev_btn is not None or current_page > 1,
    }


async def get_available_events(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch the list of available events from the site."""
    url = f"{BASE_URL}/world-rankings/overall-ranking/men"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        
        content = await resp.text()
        
        # Extract event slugs from the page
        events = []
        seen = set()
        
        matches = re.findall(
            r'"disciplineNameUrlSlug":"([^"]+)","typeNameUrlSlug":"([^"]+)","label":"([^"]+)"',
            content
        )
        
        for slug, type_slug, label in matches:
            if slug not in seen:
                seen.add(slug)
                events.append({
                    "slug": slug,
                    "type": type_slug,
                    "label": label,
                    "url_pattern": f"/world-rankings/{slug}/{{gender}}",
                })
        
        return events


async def get_available_countries(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch the list of available countries for filtering."""
    url = f"{BASE_URL}/world-rankings/overall-ranking/men"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        
        content = await resp.text()
        
        # Extract country codes from the page
        countries = []
        
        # Find the countries section in the toplistParameters
        match = re.search(r'"regionType":"countries","values":\[([^\]]+)\]', content)
        if match:
            country_str = match.group(1)
            country_matches = re.findall(r'"value":"([^"]+)","label":"([^"]+)"', country_str)
            for code, name in country_matches:
                countries.append({"code": code, "name": name})
        
        return countries


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute World Athletics rankings query.
    
    Functions:
    - get_rankings: Get rankings for a specific event and gender
    - get_events: List available events
    - get_countries: List available countries for filtering
    """
    function = params.get("function", "")
    
    try:
        if function == "get_rankings":
            return await execute_get_rankings(params)
        elif function == "get_events":
            return await execute_get_events(params)
        elif function == "get_countries":
            return await execute_get_countries(params)
        else:
            return {"error": f"Unknown function: {function}"}
    
    except Exception as e:
        return {"error": str(e), "function": function}


async def execute_get_rankings(params: dict[str, Any]) -> dict[str, Any]:
    """Get rankings for a specific event and gender."""
    event = params.get("event", "overall")
    gender = params.get("gender", "men")
    page = int(params.get("page", 1))
    limit = int(params.get("limit", 100))
    region_type = params.get("region_type")
    region = params.get("region")
    age_category = params.get("age_category")
    
    # Validate gender
    if gender not in ["men", "women"]:
        return {"error": f"Invalid gender: {gender}. Must be 'men' or 'women'"}
    
    # Validate age category if provided
    if age_category and age_category not in AGE_CATEGORIES:
        return {"error": f"Invalid age_category: {age_category}. Must be one of: {list(AGE_CATEGORIES.keys())}"}
    
    # Validate region type if provided
    if region_type and region_type not in REGION_TYPES:
        return {"error": f"Invalid region_type: {region_type}. Must be one of: {list(REGION_TYPES.keys())}"}
    
    all_rankings = []
    current_page = page
    total_pages = 1
    
    async with aiohttp.ClientSession() as session:
        # Fetch pages until we have enough results or run out of pages
        while len(all_rankings) < limit and current_page <= total_pages:
            rankings, pagination = await fetch_page(
                session,
                event=event,
                gender=gender,
                page=current_page,
                region_type=region_type,
                region=region,
                age_category=age_category,
            )
            
            all_rankings.extend(rankings)
            total_pages = pagination["total_pages"]
            
            if not pagination["has_next"]:
                break
            
            current_page += 1
    
    # Trim to limit
    all_rankings = all_rankings[:limit]
    
    return {
        "success": True,
        "event": event,
        "gender": gender,
        "page_start": page,
        "page_end": current_page,
        "total_pages": total_pages,
        "count": len(all_rankings),
        "rankings": all_rankings,
    }


async def execute_get_events(params: dict[str, Any]) -> dict[str, Any]:
    """Get list of available events."""
    async with aiohttp.ClientSession() as session:
        events = await get_available_events(session)
    
    return {
        "success": True,
        "count": len(events),
        "events": events,
        "common_events": {k: v for k, v in EVENT_SLUGS.items()},
    }


async def execute_get_countries(params: dict[str, Any]) -> dict[str, Any]:
    """Get list of available countries for filtering."""
    async with aiohttp.ClientSession() as session:
        countries = await get_available_countries(session)
    
    return {
        "success": True,
        "count": len(countries),
        "countries": countries,
        "areas": AREAS,
    }