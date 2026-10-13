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

Note: Requests use a narrowly scoped HTTP session so execution does not need
browser or subprocess privileges.
The API category filter does not work, so we filter client-side.
Country names are embedded in site titles as "Site Name (Country)".
"""

import re
from typing import Any
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup


class UNESCOWhcClient:
    """Client for UNESCO World Heritage Centre data over direct HTTP."""

    BASE_URL = "https://whc.unesco.org"

    # Category mapping
    CATEGORIES = {0: "Unknown", 1: "Cultural", 2: "Natural", 3: "Mixed"}

    # Region mapping
    REGIONS = {
        1: "Africa",
        2: "Arab States",
        3: "Asia and the Pacific",
        4: "Europe and North America",
        5: "Latin America and the Caribbean",
    }

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._initialized = False

    async def __aenter__(self):
        await self.init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init_session(self):
        """Initialize an HTTP session limited by the Skill Execution policy."""
        if self._initialized:
            return

        timeout = aiohttp.ClientTimeout(total=60)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
            },
        )
        self._initialized = True

    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            self._initialized = False

    async def fetch_geojson(
        self,
        country_code: str | None = None,
        search: str | None = None,
        category: int | None = None,
        region: int | None = None,
        in_danger: bool = False,
        with_components: bool = True,
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
            assert self._session is not None
            async with self._session.get(url) as response:
                if response.status >= 400:
                    return {"error": f"HTTP {response.status}"}
                result = await response.json(content_type=None)
                if not isinstance(result, dict):
                    return {"error": "UNESCO GeoJSON response is not an object"}
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
                match = re.search(r"\(([^)]+)\)\s*$", title)
                if match:
                    country_from_title = match.group(1)
                    site_name = title.rsplit("(", 1)[0].strip()

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
                    "components": [],
                }

            # Add component info if this is a component
            component_name = props.get("component_name")
            if site_id and component_name:
                sites[site_id]["components"].append(
                    {
                        "name": component_name,
                        "country": props.get("component_state"),
                        "coordinates": geometry.get("coordinates"),
                    }
                )

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
            assert self._session is not None
            async with self._session.get(url) as response:
                if response.status >= 400:
                    return {
                        "error": f"HTTP {response.status}",
                        "country_code": country_code.upper(),
                    }
                html = await response.text()

            soup = BeautifulSoup(html, "html.parser")
            body = soup.get_text(" ", strip=True)
            result: dict[str, Any] = {}
            patterns = {
                "properties_inscribed": r"(\d+)\s*Properties?\s*inscribed",
                "mandates": r"(\d+)\s*Mandates?\s*to\s*the\s*World\s*Heritage\s*Committee",
                "conservation_reports": r"(\d+)\s*State\s*of\s*Conservation\s*Reports",
                "assistance_requests": r"(\d+)\s*International\s*assistance.*?requests.*?Approved",
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, body, re.IGNORECASE)
                if match:
                    result[key] = int(match.group(1))

            amount = re.search(
                r"([\d,]+)\s*International\s*assistance.*?Total\s*Amount\s*Approved",
                body,
                re.IGNORECASE,
            )
            if amount:
                result["assistance_amount_usd"] = amount.group(1).replace(",", "")
            ratification = re.search(
                r"(?:Ratification|Acceptance).*?:?\s*"
                r"([A-Z][a-z]+,?\s+\d+\s+\w+\s+\d{4})",
                body,
                re.IGNORECASE,
            )
            if ratification:
                result["ratification_date"] = ratification.group(1)
            heading = soup.find("h1")
            if heading:
                result["country_name"] = heading.get_text(" ", strip=True)
            result["country_code"] = country_code.upper()
            return result
        except Exception as e:
            return {"error": str(e), "country_code": country_code.upper()}

    async def list_sites(
        self,
        country_code: str | None = None,
        search: str | None = None,
        category: str | None = None,
        in_danger: bool = False,
        limit: int = 100,
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
            country_code=country_code, search=search, in_danger=in_danger, with_components=False
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
                "in_danger": in_danger,
            },
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

                match = re.search(r"\(([^)]+)\)\s*$", title)
                if match:
                    country_from_title = match.group(1)
                    site_name = title.rsplit("(", 1)[0].strip()

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
                    "url": f"{self.BASE_URL}/en/list/{site_id}",
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
            "countries": set(),
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

    async def search_sites(
        self, query: str, country_code: str | None = None, limit: int = 50
    ) -> dict:
        """
        Search World Heritage sites by name.

        Args:
            query: Search term
            country_code: Optional country filter
            limit: Maximum results
        """
        geojson = await self.fetch_geojson(
            search=query, country_code=country_code, with_components=False
        )

        if "error" in geojson:
            return geojson

        sites = self.parse_geojson_sites(geojson)
        sites.sort(key=lambda x: (x.get("name") or "").lower())

        return {"query": query, "total": len(sites), "sites": sites[:limit]}


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
            "available_functions": [
                "list_sites",
                "get_site",
                "get_country_stats",
                "get_statistics",
                "search_sites",
            ],
        }

    available_functions = {
        "list_sites",
        "get_site",
        "get_country_stats",
        "get_statistics",
        "search_sites",
    }
    if function not in available_functions:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": sorted(available_functions),
        }

    async with UNESCOWhcClient() as client:
        if function == "list_sites":
            country_code = params.get("country_code")
            category = params.get("category")
            in_danger = params.get("in_danger", False)
            limit = params.get("limit", 100)

            return await client.list_sites(
                country_code=country_code, category=category, in_danger=in_danger, limit=limit
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
