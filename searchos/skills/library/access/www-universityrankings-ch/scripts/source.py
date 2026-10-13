"""
University Rankings (universityrankings.ch) Access Skill

This skill retrieves university ranking data from universityrankings.ch via the 
Internet Archive (Wayback Machine), as the main site is protected by CAPTCHA.

The site provides rankings from multiple systems:
- QS World University Rankings
- Times Higher Education (THE) World University Rankings
- Shanghai Ranking (ARWU)
- Leiden Ranking

Data is retrieved via Wayback Machine archival snapshots.
"""

import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import quote


# Base URL for Wayback Machine archives
ARCHIVE_BASE = "https://web.archive.org/web/2024/http://www.universityrankings.ch"

# Available ranking systems
RANKING_SYSTEMS = ["QS", "Times", "Shanghai", "Leiden"]

# Default years per system
DEFAULT_YEARS = {
    "QS": ["2025", "2024", "2023", "2022", "2021", "2020"],
    "Times": ["2025", "2024", "2023", "2022", "2021", "2020"],
    "Shanghai": ["2024", "2023", "2022", "2021", "2020"],
    "Leiden": ["2024", "2023", "2022", "2021", "2020"],
}


class UniversityRankingsClient:
    """Client for fetching university ranking data from Wayback Machine archives."""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=60.0,
            verify=False,
            follow_redirects=True,
            headers=self.headers,
        )
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def _fetch_page(self, path: str) -> BeautifulSoup:
        """Fetch a page from the archive and return parsed BeautifulSoup."""
        url = f"{ARCHIVE_BASE}{path}"
        try:
            resp = await self.client.get(url, timeout=30.0)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, 'html.parser')
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"HTTP error fetching {url}: {e.response.status_code}")
        except httpx.HTTPError as e:
            raise RuntimeError(f"Network error fetching {url}: {e}")
    
    async def get_rankings(
        self, 
        system: str, 
        year: str, 
        limit: int = 100
    ) -> dict[str, Any]:
        """
        Get university rankings for a specific system and year.
        
        Args:
            system: Ranking system (QS, Times, Shanghai, Leiden)
            year: Year of the ranking (e.g., "2024")
            limit: Maximum number of results to return
            
        Returns:
            Dictionary with ranking data
        """
        if system not in RANKING_SYSTEMS:
            return {
                "error": f"Invalid ranking system: {system}",
                "available_systems": RANKING_SYSTEMS,
            }
        
        try:
            soup = await self._fetch_page(f"/results/{system}/{year}")
            
            # Find the ranking table
            table = soup.find('table', {'id': 'RankingResults'})
            if not table:
                return {
                    "error": f"No ranking table found for {system} {year}",
                    "system": system,
                    "year": year,
                }
            
            rows = table.find_all('tr', class_='ranking_row')
            rankings = []
            
            for row in rows[:limit]:
                try:
                    # Get position
                    position_meta = row.find('meta', itemprop='position')
                    position = int(position_meta.get('content')) if position_meta else None
                    
                    # Get rank display
                    rank_span = row.find('span', class_='rank')
                    rank = rank_span.get_text(strip=True) if rank_span else str(position)
                    
                    # Get trend indicator
                    trend_div = row.find('div', class_='stable') or \
                               row.find('div', class_='up') or \
                               row.find('div', class_='down') or \
                               row.find('div', class_='new')
                    trend = ""
                    trend_description = ""
                    if trend_div:
                        trend = trend_div.get_text(strip=True)
                        if hasattr(trend_div, 'get'):
                            trend_description = trend_div.get('title', '')
                        trend_class = trend_div.get('class', [''])[0] if hasattr(trend_div, 'get') else ''
                        if trend_class == 'stable':
                            trend_description = f"stable (no change from previous year)"
                        elif trend_class == 'up':
                            trend_description = f"moved up {trend} positions"
                        elif trend_class == 'down':
                            trend_description = f"moved down {trend} positions"
                        elif trend_class == 'new':
                            trend_description = "new to ranking"
                    
                    # Get institution name
                    name_span = row.find('span', itemprop='name')
                    name = name_span.get_text(strip=True) if name_span else ""
                    
                    # Get country
                    country_img = row.find('img', class_='flag')
                    country = country_img.get('alt', '') if country_img else ""
                    
                    # Get institution URL
                    inst_link = row.find('a', itemprop='url')
                    inst_url = inst_link.get('href', '') if inst_link else ""
                    
                    # Extract institution ID from URL
                    inst_id = ""
                    if inst_url and '/institutions/' in inst_url:
                        # Extract from Wayback URL or direct URL
                        inst_id = inst_url.split('/institutions/')[-1].split('?')[0]
                    
                    rankings.append({
                        "position": position,
                        "rank": rank,
                        "institution": name,
                        "country": country,
                        "trend": trend,
                        "trend_description": trend_description,
                        "institution_id": inst_id,
                    })
                    
                except Exception:
                    continue
            
            return {
                "success": True,
                "system": system,
                "year": year,
                "total_results": len(rankings),
                "rankings": rankings,
            }
            
        except RuntimeError as e:
            return {"error": str(e), "system": system, "year": year}
        except Exception as e:
            return {"error": f"Failed to fetch rankings: {e}", "system": system, "year": year}
    
    async def get_institution(self, institution_id: str) -> dict[str, Any]:
        """
        Get detailed ranking history for a specific institution.
        
        Args:
            institution_id: Institution ID (e.g., id6272-massachusetts_institute_of_technology_mit-usa)
            
        Returns:
            Dictionary with institution ranking history
        """
        try:
            soup = await self._fetch_page(f"/institutions/{institution_id}")
            
            # Get institution name
            title = soup.find('h1')
            name = title.get_text(strip=True) if title else institution_id
            
            # Extract clean name from ID if title not found
            if not name or 'http' in name.lower():
                name = institution_id.split('-', 1)[-1].replace('_', ' ').replace('-usa', '').title()
            
            # Find ranking history table
            table = soup.find('table')
            if not table:
                return {
                    "error": "No ranking history found",
                    "institution_id": institution_id,
                    "name": name,
                }
            
            rows = table.find_all('tr')
            
            # Parse headers
            header_row = rows[0].find_all(['th', 'td'])
            systems = [h.get_text(strip=True) for h in header_row if h.get_text(strip=True)]
            
            # Parse ranking data by year
            ranking_history = []
            for row in rows[1:]:
                cells = row.find_all('td')
                if cells and len(cells) >= 2:
                    year = cells[0].get_text(strip=True)
                    if year.isdigit():
                        year_data = {"year": year}
                        for i, cell in enumerate(cells[1:], 1):
                            if i <= len(systems):
                                value = cell.get_text(strip=True)
                                if value and value != '-':
                                    year_data[systems[i-1] if i-1 < len(systems) else f"col_{i}"] = value
                        ranking_history.append(year_data)
            
            return {
                "success": True,
                "institution_id": institution_id,
                "name": name,
                "ranking_history": ranking_history,
                "available_systems": [s for s in systems if s in RANKING_SYSTEMS],
            }
            
        except RuntimeError as e:
            return {"error": str(e), "institution_id": institution_id}
        except Exception as e:
            return {"error": f"Failed to fetch institution: {e}", "institution_id": institution_id}
    
    async def search_institutions(
        self,
        system: str,
        year: str,
        query: Optional[str] = None,
        country: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Search for institutions in a ranking by name or country.
        
        Args:
            system: Ranking system
            year: Year
            query: Search query for institution name
            country: Filter by country
            
        Returns:
            Dictionary with matching institutions
        """
        if system not in RANKING_SYSTEMS:
            return {
                "error": f"Invalid ranking system: {system}",
                "available_systems": RANKING_SYSTEMS,
            }
        
        result = await self.get_rankings(system, year, limit=500)
        
        if "error" in result:
            return result
        
        rankings = result.get("rankings", [])
        
        # Filter by query
        if query:
            query_lower = query.lower()
            rankings = [
                r for r in rankings
                if query_lower in r.get("institution", "").lower()
            ]
        
        # Filter by country
        if country:
            country_lower = country.lower()
            rankings = [
                r for r in rankings
                if country_lower in r.get("country", "").lower()
            ]
        
        return {
            "success": True,
            "system": system,
            "year": year,
            "query": query,
            "country": country,
            "total_results": len(rankings),
            "results": rankings,
        }
    
    async def list_available_years(self, system: str) -> dict[str, Any]:
        """
        List available years for a ranking system.
        
        Args:
            system: Ranking system
            
        Returns:
            Dictionary with available years
        """
        if system not in RANKING_SYSTEMS:
            return {
                "error": f"Invalid ranking system: {system}",
                "available_systems": RANKING_SYSTEMS,
            }
        
        # Return known years (from archive data)
        return {
            "success": True,
            "system": system,
            "years": DEFAULT_YEARS.get(system, []),
            "note": "Years based on archived data availability",
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a function from this skill.
    
    Args:
        params: Dictionary containing:
            - function: Name of function to call
            - Plus function-specific parameters
        ctx: Optional context (unused)
        
    Returns:
        Dictionary with results or error
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter 'function'"}
    
    async with UniversityRankingsClient() as client:
        if function == "get_rankings":
            system = params.get("system")
            year = params.get("year")
            limit = params.get("limit", 100)
            
            if not system:
                return {"error": "Missing required parameter 'system'", "available_systems": RANKING_SYSTEMS}
            if not year:
                return {"error": "Missing required parameter 'year'"}
            
            return await client.get_rankings(system, year, limit)
        
        elif function == "get_institution":
            institution_id = params.get("institution_id")
            
            if not institution_id:
                return {"error": "Missing required parameter 'institution_id'"}
            
            return await client.get_institution(institution_id)
        
        elif function == "search_institutions":
            system = params.get("system")
            year = params.get("year")
            query = params.get("query")
            country = params.get("country")
            
            if not system:
                return {"error": "Missing required parameter 'system'", "available_systems": RANKING_SYSTEMS}
            if not year:
                return {"error": "Missing required parameter 'year'"}
            
            return await client.search_institutions(system, year, query, country)
        
        elif function == "list_available_years":
            system = params.get("system")
            
            if not system:
                return {"error": "Missing required parameter 'system'", "available_systems": RANKING_SYSTEMS}
            
            return await client.list_available_years(system)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_rankings",
                    "get_institution",
                    "search_institutions",
                    "list_available_years",
                ],
            }