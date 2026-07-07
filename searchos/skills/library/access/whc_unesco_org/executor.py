"""
UNESCO World Heritage Centre Access Skill

Provides access to the UNESCO World Heritage Convention database including:
- World Heritage List sites with GeoJSON data
- States Parties statistics
- Sites in Danger
- Search and filtering capabilities

APIs discovered:
- /en/list/?mode=geojson - Returns all sites as GeoJSON with filtering options
- /en/statesparties/{code} - Country statistics (HTML scraping)

Note: Site uses Cloudflare protection, requires browser session for API access.
The API category filter does not work, so we filter client-side.
Country names are embedded in site titles as "Site Name (Country)".
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class UNESCOWhcClient:
    """Client for UNESCO World Heritage Centre data access using Playwright."""
    
    BASE_URL = "https://whc.unesco.org"
    
    # Category mapping
    CATEGORIES = {
        0: "Unknown",
        1: "Cultural",
        2: "Natural", 
        3: "Mixed"
    }
    
    # Region mapping
    REGIONS = {
        1: "Africa",
        2: "Arab States",
        3: "Asia and the Pacific",
        4: "Europe and North America",
        5: "Latin America and the Caribbean"
    }
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._initialized = False
        
    async def __aenter__(self):
        await self.init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def init_session(self):
        """Initialize browser session."""
        if self._initialized:
            return
            
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        
        # Establish session by visiting a page
        await self._page.goto(f"{self.BASE_URL}/en/statesparties/us", wait_until="load", timeout=60000)
        await asyncio.sleep(1)
        self._initialized = True
    
    async def close(self):
        """Close browser session."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
            self._initialized = False
    
    async def fetch_geojson(
        self,
        country_code: Optional[str] = None,
        search: Optional[str] = None,
        category: Optional[int] = None,
        region: Optional[int] = None,
        in_danger: bool = False,
        with_components: bool = True
    ) -> dict:
        """
        Fetch World Heritage sites as GeoJSON.
        
        Args:
            country_code: ISO 3166-1 alpha-2 country code (e.g., 'us', 'fr', 'jp')
            search: Search term for site names
            category: 1=Cultural, 2=Natural, 3=Mixed (note: filtered client-side)
            region: 1=Africa, 2=Arab States, 3=Asia-Pacific, 4=Europe, 5=Latin America
            in_danger: Only return sites on the List of World Heritage in Danger
            with_components: Include component-level data for serial properties
        """
        if not self._initialized:
            await self.init_session()
        
        params = {"mode": "geojson"}
        
        if country_code:
            params["search_iso_code"] = country_code.lower()
        if search:
            params["search"] = search
        # Note: category filter doesn't work on API, we filter client-side
        if region:
            params["region"] = str(region)
        if in_danger:
            params["danger"] = "1"
        if with_components:
            params["components"] = "1"
        else:
            params["components"] = "0"
        
        url = f"{self.BASE_URL}/en/list/?{urlencode(params)}"
        
        try:
            result = await self._page.evaluate(f'''
                async () => {{
                    try {{
                        const response = await fetch('{url}');
                        if (!response.ok) {{
                            return {{error: `HTTP ${{response.status}}`}};
                        }}
                        return await response.json();
                    }} catch (e) {{
                        return {{error: e.toString()}};
                    }}
                }}
            ''')
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def parse_geojson_sites(self, geojson: dict) -> list:
        """Parse GeoJSON response into a list of unique sites."""
        if "error" in geojson or not isinstance(geojson, dict):
            return []
        
        features = geojson.get("features", [])
        sites = {}
        
        for f in features:
            props = f.get("properties", {})
            site_id = props.get("id_no")
            geometry = f.get("geometry", {})
            
            if site_id and site_id not in sites:
                cat_num = props.get("cat", 0)
                
                # Parse title to extract site name and country
                title = props.get("title", "")
                country_from_title = None
                site_name = title
                
                # Pattern: "Site Name (Country)" 
                match = re.search(r'\(([^)]+)\)\s*$', title)
                if match:
                    country_from_title = match.group(1)
                    site_name = title.rsplit('(', 1)[0].strip()
                
                sites[site_id] = {
                    "id": site_id,
                    "name": site_name,
                    "full_title": title,
                    "category": self.CATEGORIES.get(cat_num, "Unknown"),
                    "category_id": cat_num,
                    "in_danger": bool(props.get("danger")),
                    "country": country_from_title or props.get("component_state"),
                    "geometry_type": geometry.get("type"),
                    "coordinates": geometry.get("coordinates"),
                    "components": []
                }
            
            # Add component info if this is a component
            component_name = props.get("component_name")
            if site_id and component_name:
                sites[site_id]["components"].append({
                    "name": component_name,
                    "country": props.get("component_state"),
                    "coordinates": geometry.get("coordinates")
                })
        
        return list(sites.values())
    
    async def fetch_states_parties(self, country_code: str) -> dict:
        """
        Fetch States Parties statistics for a country.
        
        Args:
            country_code: ISO 3166-1 alpha-2 country code
        """
        if not self._initialized:
            await self.init_session()
        
        url = f"{self.BASE_URL}/en/statesparties/{country_code.lower()}"
        
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(0.5)
            
            result = await self._page.evaluate('''
                () => {
                    const body = document.body.innerText;
                    const res = {};
                    
                    // Extract statistics using patterns
                    const propsMatch = body.match(/(\\d+)\\s*Properties?\\s*inscribed/i);
                    if (propsMatch) res.properties_inscribed = parseInt(propsMatch[1]);
                    
                    const mandatesMatch = body.match(/(\\d+)\\s*Mandates?\\s*to\\s*the\\s*World\\s*Heritage\\s*Committee/i);
                    if (mandatesMatch) res.mandates = parseInt(mandatesMatch[1]);
                    
                    const reportsMatch = body.match(/(\\d+)\\s*State\\s*of\\s*Conservation\\s*Reports/i);
                    if (reportsMatch) res.conservation_reports = parseInt(reportsMatch[1]);
                    
                    const assistanceMatch = body.match(/(\\d+)\\s*International\\s*assistance.*?requests.*?Approved/is);
                    if (assistanceMatch) res.assistance_requests = parseInt(assistanceMatch[1]);
                    
                    const amountMatch = body.match(/([\\d,]+)\\s*International\\s*assistance.*?Total\\s*Amount\\s*Approved/i);
                    if (amountMatch) res.assistance_amount_usd = amountMatch[1].replace(/,/g, '');
                    
                    const ratMatch = body.match(/(?:Ratification|Acceptance).*?:?\\s*([A-Z][a-z]+,?\\s+\\d+\\s+\\w+\\s+\\d{4})/i);
                    if (ratMatch) res.ratification_date = ratMatch[1];
                    
                    // Country name from h1
                    const h1 = document.querySelector('h1');
                    if (h1) res.country_name = h1.textContent.trim();
                    
                    return res;
                }
            ''')
            
            result["country_code"] = country_code.upper()
            return result
            
        except Exception as e:
            return {"error": str(e), "country_code": country_code.upper()}
    
    async def list_sites(
        self,
        country_code: Optional[str] = None,
        search: Optional[str] = None,
        category: Optional[str] = None,
        in_danger: bool = False,
        limit: int = 100
    ) -> dict:
        """
        List World Heritage sites with optional filters.
        
        Args:
            country_code: Filter by ISO country code
            search: Search term for site names
            category: Filter by category: 'cultural', 'natural', or 'mixed'
            in_danger: Only return sites in danger
            limit: Maximum number of results
        """
        geojson = await self.fetch_geojson(
            country_code=country_code,
            search=search,
            in_danger=in_danger,
            with_components=False
        )
        
        if "error" in geojson:
            return geojson
        
        sites = self.parse_geojson_sites(geojson)
        
        # Filter by category client-side (API filter doesn't work)
        if category:
            category_lower = category.lower()
            sites = [s for s in sites if s.get("category", "").lower() == category_lower]
        
        # Sort by name
        sites.sort(key=lambda x: (x.get("name") or "").lower())
        
        return {
            "total": len(sites),
            "sites": sites[:limit],
            "filters": {
                "country_code": country_code,
                "search": search,
                "category": category,
                "in_danger": in_danger
            }
        }
    
    async def get_site_details(self, site_id: int) -> dict:
        """
        Get details for a specific site by ID.
        Note: Site detail pages are protected by Cloudflare.
        Returns basic info from GeoJSON data.
        """
        geojson = await self.fetch_geojson(with_components=True)
        
        if "error" in geojson:
            return geojson
        
        for f in geojson.get("features", []):
            props = f.get("properties", {})
            if props.get("id_no") == site_id:
                cat_num = props.get("cat", 0)
                geometry = f.get("geometry", {})
                
                # Parse title
                title = props.get("title", "")
                country_from_title = None
                site_name = title
                
                match = re.search(r'\(([^)]+)\)\s*$', title)
                if match:
                    country_from_title = match.group(1)
                    site_name = title.rsplit('(', 1)[0].strip()
                
                return {
                    "id": site_id,
                    "name": site_name,
                    "full_title": title,
                    "category": self.CATEGORIES.get(cat_num, "Unknown"),
                    "category_id": cat_num,
                    "in_danger": bool(props.get("danger")),
                    "country": country_from_title or props.get("component_state"),
                    "geometry_type": geometry.get("type"),
                    "coordinates": geometry.get("coordinates"),
                    "component_name": props.get("component_name"),
                    "url": f"{self.BASE_URL}/en/list/{site_id}"
                }
        
        return {"error": f"Site {site_id} not found"}
    
    async def get_statistics(self) -> dict:
        """Get overall World Heritage statistics."""
        geojson = await self.fetch_geojson(with_components=False)
        
        if "error" in geojson:
            return geojson
        
        sites = self.parse_geojson_sites(geojson)
        
        stats = {
            "total_sites": len(sites),
            "by_category": {},
            "sites_in_danger": 0,
            "countries": set()
        }
        
        for site in sites:
            cat = site.get("category", "Unknown")
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            
            if site.get("in_danger"):
                stats["sites_in_danger"] += 1
            
            if site.get("country"):
                stats["countries"].add(site["country"])
        
        stats["countries_count"] = len(stats["countries"])
        stats["countries"] = sorted(list(stats["countries"]))
        
        return stats
    
    async def search_sites(self, query: str, country_code: Optional[str] = None, limit: int = 50) -> dict:
        """
        Search World Heritage sites by name.
        
        Args:
            query: Search term
            country_code: Optional country filter
            limit: Maximum results
        """
        geojson = await self.fetch_geojson(
            search=query,
            country_code=country_code,
            with_components=False
        )
        
        if "error" in geojson:
            return geojson
        
        sites = self.parse_geojson_sites(geojson)
        sites.sort(key=lambda x: (x.get("name") or "").lower())
        
        return {
            "query": query,
            "total": len(sites),
            "sites": sites[:limit]
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute UNESCO World Heritage Centre queries.
    
    Functions:
    - list_sites: List World Heritage sites with filters
    - get_site: Get details for a specific site
    - get_country_stats: Get statistics for a country
    - get_statistics: Get overall World Heritage statistics
    - search_sites: Search sites by name
    
    Parameters by function:
    
    list_sites:
        - country_code: Optional ISO country code filter (e.g., 'us', 'fr')
        - category: Optional category filter ('cultural', 'natural', 'mixed')
        - in_danger: Boolean to filter sites in danger only
        - limit: Maximum number of results (default: 100)
    
    get_site:
        - site_id: Required site ID number
    
    get_country_stats:
        - country_code: Required ISO country code
    
    get_statistics: No parameters
    
    search_sites:
        - query: Required search term
        - country_code: Optional ISO country code filter
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing required parameter 'function'",
            "available_functions": ["list_sites", "get_site", "get_country_stats", "get_statistics", "search_sites"]
        }
    
    async with UNESCOWhcClient() as client:
        if function == "list_sites":
            country_code = params.get("country_code")
            category = params.get("category")
            in_danger = params.get("in_danger", False)
            limit = params.get("limit", 100)
            
            return await client.list_sites(
                country_code=country_code,
                category=category,
                in_danger=in_danger,
                limit=limit
            )
        
        elif function == "get_site":
            site_id = params.get("site_id")
            
            if not site_id:
                return {"error": "Missing required parameter 'site_id'"}
            
            try:
                site_id = int(site_id)
            except (ValueError, TypeError):
                return {"error": f"Invalid site_id: {site_id}. Must be a number."}
            
            return await client.get_site_details(site_id)
        
        elif function == "get_country_stats":
            country_code = params.get("country_code")
            
            if not country_code:
                return {"error": "Missing required parameter 'country_code'"}
            
            return await client.fetch_states_parties(country_code)
        
        elif function == "get_statistics":
            return await client.get_statistics()
        
        elif function == "search_sites":
            query = params.get("query")
            
            if not query:
                return {"error": "Missing required parameter 'query'"}
            
            country_code = params.get("country_code")
            limit = params.get("limit", 50)
            
            return await client.search_sites(query, country_code, limit)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": ["list_sites", "get_site", "get_country_stats", "get_statistics", "search_sites"]
            }