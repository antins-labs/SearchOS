"""
World Aquatics API Access Skill

Provides access to World Aquatics (formerly FINA) database for:
- Athlete profiles, medals, and competition results
- Competition details, events, and medal tables
- Athlete search functionality

API Base: https://api.worldaquatics.com/fina
"""

import aiohttp
from typing import Any, Optional
from datetime import datetime


class WorldAquaticsAPI:
    """World Aquatics API client"""
    
    BASE_URL = "https://api.worldaquatics.com/fina"
    CONTENT_URL = "https://api.worldaquatics.com/content/fina"
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Origin': 'https://www.worldaquatics.com',
            'Referer': 'https://www.worldaquatics.com/'
        }
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(self, url: str) -> dict:
        """Make API request and return JSON data"""
        session = await self._get_session()
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 404:
                return {"error": "Not found", "status": 404}
            else:
                text = await resp.text()
                return {"error": f"API error: {resp.status}", "status": resp.status, "body": text[:500]}
    
    # ==== ATHLETE ENDPOINTS ====
    
    async def get_athlete(self, athlete_id: int) -> dict:
        """Get athlete profile by ID"""
        url = f"{self.BASE_URL}/athletes/{athlete_id}"
        return await self._request(url)
    
    async def get_athlete_medals(self, athlete_id: int) -> dict:
        """Get athlete medal summary"""
        url = f"{self.BASE_URL}/athletes/{athlete_id}/medals"
        return await self._request(url)
    
    async def get_athlete_results(self, athlete_id: int) -> dict:
        """Get athlete competition results history"""
        url = f"{self.BASE_URL}/athletes/{athlete_id}/results"
        return await self._request(url)
    
    async def search_athletes(
        self,
        name: Optional[str] = None,
        limit: int = 20,
        page: int = 0
    ) -> dict:
        """
        Search athletes by name
        
        Args:
            name: Athlete name to search (last name or full name)
            limit: Maximum results per page (default 20)
            page: Page number (default 0)
        """
        params = [f"limit={limit}", f"page={page}"]
        if name:
            params.append(f"name={name}")
        
        url = f"{self.BASE_URL}/athletes?{'&'.join(params)}"
        return await self._request(url)
    
    # ==== COMPETITION ENDPOINTS ====
    
    async def get_competition(self, competition_id: int) -> dict:
        """Get competition details by ID"""
        url = f"{self.BASE_URL}/competitions/{competition_id}"
        return await self._request(url)
    
    async def get_competition_events(self, competition_id: int) -> dict:
        """Get competition events structure with heats/rounds"""
        url = f"{self.BASE_URL}/competitions/{competition_id}/events"
        return await self._request(url)
    
    async def get_competition_medals(self, competition_id: int) -> dict:
        """Get competition medal table"""
        url = f"{self.BASE_URL}/competitions/{competition_id}/medals"
        return await self._request(url)
    
    async def list_competitions(
        self,
        limit: int = 20,
        page: int = 0
    ) -> dict:
        """
        List competitions
        
        Args:
            limit: Maximum results per page
            page: Page number
        """
        url = f"{self.BASE_URL}/competitions?limit={limit}&page={page}"
        return await self._request(url)
    
    # ==== LIVE RESULTS ====
    
    async def get_live_results(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> dict:
        """
        Get live results for ongoing competitions
        
        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)
        """
        if not date_from or not date_to:
            # Default to current week
            today = datetime.utcnow()
            date_from = today.strftime("%Y-%m-%dT00:00:00Z")
            date_to = today.strftime("%Y-%m-%dT23:59:59Z")
        
        url = f"{self.BASE_URL}/results/live?venueDateFrom={date_from}&venueDateTo={date_to}"
        return await self._request(url)


# ==== EXECUTOR FUNCTIONS ====

async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute World Aquatics API request
    
    Required params:
        function: One of 'get_athlete', 'get_athlete_medals', 'get_athlete_results',
                  'search_athletes', 'get_competition', 'get_competition_events',
                  'get_competition_medals', 'list_competitions', 'get_live_results'
    
    Additional params depend on function:
        - get_athlete: athlete_id (required)
        - get_athlete_medals: athlete_id (required)
        - get_athlete_results: athlete_id (required)
        - search_athletes: name (optional), limit (default 20), page (default 0)
        - get_competition: competition_id (required)
        - get_competition_events: competition_id (required)
        - get_competition_medals: competition_id (required)
        - list_competitions: limit (default 20), page (default 0)
        - get_live_results: date_from, date_to (optional, ISO format)
    
    Returns:
        dict with 'success': True and 'data': {...} on success
        dict with 'success': False and 'error': '...' on failure
    """
    function = params.get("function")
    if not function:
        return {"success": False, "error": "Missing required parameter: function"}
    
    api = WorldAquaticsAPI()
    
    try:
        result = None
        
        if function == "get_athlete":
            athlete_id = params.get("athlete_id")
            if not athlete_id:
                return {"success": False, "error": "Missing required parameter: athlete_id"}
            result = await api.get_athlete(int(athlete_id))
        
        elif function == "get_athlete_medals":
            athlete_id = params.get("athlete_id")
            if not athlete_id:
                return {"success": False, "error": "Missing required parameter: athlete_id"}
            result = await api.get_athlete_medals(int(athlete_id))
        
        elif function == "get_athlete_results":
            athlete_id = params.get("athlete_id")
            if not athlete_id:
                return {"success": False, "error": "Missing required parameter: athlete_id"}
            result = await api.get_athlete_results(int(athlete_id))
        
        elif function == "search_athletes":
            result = await api.search_athletes(
                name=params.get("name"),
                limit=params.get("limit", 20),
                page=params.get("page", 0)
            )
        
        elif function == "get_competition":
            competition_id = params.get("competition_id")
            if not competition_id:
                return {"success": False, "error": "Missing required parameter: competition_id"}
            result = await api.get_competition(int(competition_id))
        
        elif function == "get_competition_events":
            competition_id = params.get("competition_id")
            if not competition_id:
                return {"success": False, "error": "Missing required parameter: competition_id"}
            result = await api.get_competition_events(int(competition_id))
        
        elif function == "get_competition_medals":
            competition_id = params.get("competition_id")
            if not competition_id:
                return {"success": False, "error": "Missing required parameter: competition_id"}
            result = await api.get_competition_medals(int(competition_id))
        
        elif function == "list_competitions":
            result = await api.list_competitions(
                limit=params.get("limit", 20),
                page=params.get("page", 0)
            )
        
        elif function == "get_live_results":
            result = await api.get_live_results(
                date_from=params.get("date_from"),
                date_to=params.get("date_to")
            )
        
        else:
            return {"success": False, "error": f"Unknown function: {function}"}
        
        # Check for API error
        if "error" in result:
            return {"success": False, "error": result["error"]}
        
        return {"success": True, "data": result}
    
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    finally:
        await api.close()