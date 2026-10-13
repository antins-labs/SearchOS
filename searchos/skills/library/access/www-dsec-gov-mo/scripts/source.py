"""
DSEC (Macau Statistics and Census Service) Access Skill

Provides access to Macau official statistics including:
- Tourism statistics (visitor arrivals, hotel occupancy, visitor expenditure)
- Gaming sector statistics
- Demographic statistics
- National accounts (GDP, GNI)
- Price indices
- Labour statistics
"""

import aiohttp
import asyncio
import json
import re
from typing import Any, Optional
from datetime import datetime


class DSECClient:
    """Client for accessing DSEC Macau statistics API"""
    
    BASE_URL = "https://www.dsec.gov.mo"
    STATISTICS_JSON_URL = f"{BASE_URL}/StatisticsJSON"
    
    # Known category file mappings
    CATEGORIES = {
        "TourismAndServices": [
            "TourismStatistics", "VisitorArrivals", "PackageToursAndHotelOccupancyRate",
            "VisitorExpenditureSurvey", "TouristPriceIndex", "GamingSectorSurvey",
            "MICEStatistics", "TourismSatelliteAccount"
        ],
        "General": [
            "YearbookOfStatistics", "MacaoInFigures", "SIED",
            "MacaoEconomicBulletin", "MonthlyBulletinOfStatistics"
        ],
        "NationalAccounts": [
            "GrossDomesticProduct", "Gross-Domestic-Product-(By-Production-Approach)--A",
            "GrossNationalIncome", "BalanceOfPayments"
        ],
        "Demographic": [
            "DemographicStatistics", "MacaoResidentPopulationProjections",
            "PopulationCensus", "GlobalResultsOfBy-Census", "HouseholdBudgetSurvey"
        ],
    }
    
    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
    async def _fetch_json(self, session: aiohttp.ClientSession, url: str) -> Optional[Any]:
        """Fetch JSON from URL, handling BOM"""
        try:
            async with session.get(url, ssl=False, timeout=self.timeout) as response:
                if response.status == 200:
                    text = await response.text()
                    # Remove BOM if present
                    if text.startswith('\ufeff'):
                        text = text[1:]
                    return json.loads(text)
                return None
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None
    
    async def _get_all_releases(self, session: aiohttp.ClientSession, 
                                 category: str, language: str = "en-US") -> Optional[dict]:
        """Fetch all releases for a category"""
        filename = f"AllReleases_{language}_{category}.json?v=1.9.18"
        url = f"{self.STATISTICS_JSON_URL}/{filename}"
        return await self._fetch_json(session, url)
    
    async def _get_key_indicators(self, session: aiohttp.ClientSession,
                                   language: str = "en-US") -> Optional[list]:
        """Fetch key indicators"""
        filename = f"KeyIndicator_{language}.json?v=1.9.18"
        url = f"{self.STATISTICS_JSON_URL}/{filename}"
        return await self._fetch_json(session, url)


# Initialize client
_client = DSECClient()


async def list_categories(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all available statistical categories and their topics
    
    Args:
        params: Dictionary with optional 'language' key (default: en-US)
        ctx: Context object (unused)
    
    Returns:
        Dictionary with categories and topics
    """
    language = params.get("language", "en-US")
    
    async with aiohttp.ClientSession() as session:
        results = {"categories": {}, "language": language}
        
        # Fetch each category file
        tasks = []
        for category_name in _client.CATEGORIES.keys():
            filename = f"AllReleases_{language}_{category_name}.json?v=1.9.18"
            url = f"{_client.STATISTICS_JSON_URL}/{filename}"
            tasks.append((category_name, _client._fetch_json(session, url)))
        
        for category_name, task in tasks:
            data = await task
            if data:
                topics = []
                for topic_key, topic_data in data.items():
                    if isinstance(topic_data, dict):
                        topics.append({
                            "key": topic_key,
                            "name": topic_data.get("Name", topic_key),
                        })
                results["categories"][category_name] = topics
        
        return {"success": True, "data": results}


async def get_key_indicators(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get all key statistical indicators with latest values
    
    Args:
        params: Dictionary with optional 'language' and 'indicator_id' keys
        ctx: Context object (unused)
    
    Returns:
        Dictionary with indicators data
    """
    language = params.get("language", "en-US")
    indicator_id = params.get("indicator_id")
    
    async with aiohttp.ClientSession() as session:
        indicators = await _client._get_key_indicators(session, language)
        
        if indicators is None:
            return {"success": False, "error": "Failed to fetch key indicators"}
        
        # Filter by indicator_id if provided
        if indicator_id:
            indicators = [ind for ind in indicators if ind.get("KeyIndicatorID") == indicator_id]
        
        # Format indicators
        formatted = []
        for ind in indicators:
            formatted.append({
                "id": ind.get("KeyIndicatorID"),
                "name": ind.get("Name"),
                "value": ind.get("Value"),
                "value_with_remark": ind.get("ValueWithRemark"),
                "unit": ind.get("Unit"),
                "year": ind.get("Year"),
                "period_id": ind.get("PeriodID"),
                "period_description": ind.get("PeriodDescription"),
            })
        
        return {
            "success": True,
            "data": {
                "indicators": formatted,
                "count": len(formatted),
                "language": language,
            }
        }


async def get_statistical_releases(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get publication releases for a specific statistical topic
    
    Args:
        params: Dictionary with 'category', 'topic', and optional filters
        ctx: Context object (unused)
    
    Returns:
        Dictionary with release information
    """
    category = params.get("category")
    topic = params.get("topic")
    period_type = params.get("period_type")  # Monthly, Quarterly, Yearly
    year = params.get("year")
    language = params.get("language", "en-US")
    
    if not category or not topic:
        return {"success": False, "error": "Both 'category' and 'topic' parameters are required"}
    
    valid_periods = ["Monthly", "Quarterly", "Yearly"]
    if period_type and period_type not in valid_periods:
        return {"success": False, "error": f"period_type must be one of {valid_periods}"}
    
    async with aiohttp.ClientSession() as session:
        data = await _client._get_all_releases(session, category, language)
        
        if data is None:
            return {"success": False, "error": f"Failed to fetch data for category: {category}"}
        
        topic_data = data.get(topic)
        if not topic_data:
            return {"success": False, "error": f"Topic '{topic}' not found in category '{category}'"}
        
        container = topic_data.get("Containers", {}).get(topic, {})
        params_info = container.get("Params", {})
        publications = container.get("Publication", {})
        
        # Prepare result
        result = {
            "success": True,
            "data": {
                "topic": {
                    "key": topic,
                    "name": params_info.get("Name", topic),
                    "link": f"{_client.BASE_URL}{params_info.get('Link', '')}",
                    "guid": params_info.get("NodeGUID"),
                },
                "releases": {},
                "language": language,
            }
        }
        
        # Process publications by period type
        periods_to_process = [period_type] if period_type else valid_periods
        
        for period in periods_to_process:
            releases = publications.get(period, [])
            if not releases:
                continue
            
            # Filter by year if specified
            if year:
                releases = [r for r in releases if str(r.get("Year")) == str(year)]
            
            # Format releases
            formatted_releases = []
            for release in releases:
                formatted = {
                    "release_id": release.get("ReleaseID"),
                    "name": release.get("Name"),
                    "year": release.get("Year"),
                    "period": release.get("Period"),
                    "period_remark": release.get("PeriodRemark"),
                    "has_news": release.get("HasNews"),
                    "last_modified": datetime.fromtimestamp(release["LMD"]/1000).isoformat() if release.get("LMD") else None,
                }
                
                # Add file attachments
                files = release.get("File", [])
                if files:
                    formatted["files"] = [
                        {
                            "name": f.get("Name"),
                            "type": f.get("Type"),
                            "link": f"{_client.BASE_URL}{f.get('Link', '')}",
                        }
                        for f in files
                    ]
                
                formatted_releases.append(formatted)
            
            result["data"]["releases"][period] = {
                "count": len(formatted_releases),
                "items": formatted_releases[:50] if len(formatted_releases) > 50 else formatted_releases,
                "total_available": len(formatted_releases),
            }
        
        return result


async def get_release_detail(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get detailed information for a specific release
    
    Args:
        params: Dictionary with 'release_id' key
        ctx: Context object (unused)
    
    Returns:
        Dictionary with release details
    """
    release_id = params.get("release_id")
    
    if not release_id:
        return {"success": False, "error": "release_id parameter is required"}
    
    # Need to search through all categories to find the release
    async with aiohttp.ClientSession() as session:
        # Search in all known categories
        languages = ["en-US"]
        
        for language in languages:
            for category_name in _client.CATEGORIES.keys():
                data = await _client._get_all_releases(session, category_name, language)
                if not data:
                    continue
                
                for topic_key, topic_data in data.items():
                    if not isinstance(topic_data, dict):
                        continue
                    
                    container = topic_data.get("Containers", {}).get(topic_key, {})
                    publications = container.get("Publication", {})
                    
                    for period_type in ["Monthly", "Quarterly", "Yearly"]:
                        releases = publications.get(period_type, [])
                        for release in releases:
                            if release.get("ReleaseID") == release_id:
                                return {
                                    "success": True,
                                    "data": {
                                        "release": {
                                            "release_id": release.get("ReleaseID"),
                                            "name": release.get("Name"),
                                            "name_short": release.get("NameShort"),
                                            "year": release.get("Year"),
                                            "period": release.get("Period"),
                                            "period_type": period_type.lower(),
                                            "period_remark": release.get("PeriodRemark"),
                                            "last_modified": datetime.fromtimestamp(release["LMD"]/1000).isoformat() if release.get("LMD") else None,
                                            "has_news": release.get("HasNews"),
                                            "files": [
                                                {
                                                    "name": f.get("Name"),
                                                    "type": f.get("Type"),
                                                    "link": f"{_client.BASE_URL}{f.get('Link', '')}",
                                                    "id": f.get("Id"),
                                                }
                                                for f in release.get("File", [])
                                            ],
                                        },
                                        "topic": topic_data.get("Name"),
                                        "category": category_name,
                                    }
                                }
        
        return {"success": False, "error": f"Release with ID {release_id} not found"}


async def search_indicators(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search key indicators by name or keyword
    
    Args:
        params: Dictionary with 'query' and optional 'language' keys
        ctx: Context object (unused)
    
    Returns:
        Dictionary with matching indicators
    """
    query = params.get("query", "").lower()
    language = params.get("language", "en-US")
    
    if not query:
        return {"success": False, "error": "query parameter is required"}
    
    async with aiohttp.ClientSession() as session:
        indicators = await _client._get_key_indicators(session, language)
        
        if indicators is None:
            return {"success": False, "error": "Failed to fetch key indicators"}
        
        # Search by name
        matches = []
        for ind in indicators:
            name = ind.get("Name", "").lower()
            if query in name:
                matches.append({
                    "id": ind.get("KeyIndicatorID"),
                    "name": ind.get("Name"),
                    "value": ind.get("Value"),
                    "value_with_remark": ind.get("ValueWithRemark"),
                    "unit": ind.get("Unit"),
                    "year": ind.get("Year"),
                    "period_description": ind.get("PeriodDescription"),
                })
        
        return {
            "success": True,
            "data": {
                "query": query,
                "matches": matches,
                "count": len(matches),
                "language": language,
            }
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the DSEC access skill
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Context object
    
    Returns:
        Dictionary with results or error
    """
    function = params.get("function")
    
    if not function:
        return {"success": False, "error": "function parameter is required"}
    
    handlers = {
        "list_categories": list_categories,
        "get_key_indicators": get_key_indicators,
        "get_statistical_releases": get_statistical_releases,
        "get_release_detail": get_release_detail,
        "search_indicators": search_indicators,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {"success": False, "error": f"Unknown function: {function}. Available functions: {list(handlers.keys())}"}
    
    try:
        return await handler(params, ctx)
    except Exception as e:
        return {"success": False, "error": str(e)}


# For testing
if __name__ == "__main__":
    import sys
    
    async def test():
        # Test list categories
        print("Testing list_categories...")
        result = await list_categories({})
        print(f"Success: {result['success']}")
        if result['success']:
            for cat, topics in result['data']['categories'].items():
                print(f"  {cat}: {len(topics)} topics")
        
        # Test get key indicators
        print("\nTesting get_key_indicators...")
        result = await get_key_indicators({})
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Total indicators: {result['data']['count']}")
            for ind in result['data']['indicators'][:5]:
                print(f"  {ind['name']}: {ind['value']} {ind['unit']}")
        
        # Test search indicators
        print("\nTesting search_indicators...")
        result = await search_indicators({"query": "visitor"})
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Matches: {result['data']['count']}")
        
        # Test get statistical releases
        print("\nTesting get_statistical_releases...")
        result = await get_statistical_releases({
            "category": "TourismAndServices",
            "topic": "VisitorArrivals",
            "period_type": "Monthly",
            "year": 2026
        })
        print(f"Success: {result['success']}")
        if result['success']:
            releases = result['data'].get('releases', {}).get('Monthly', {})
            print(f"Monthly releases: {releases.get('count', 0)}")
    
    asyncio.run(test())