"""
ACI World Airport Rankings Access Skill

Fetches airport traffic rankings from ACI World blog including:
- Top airports by passenger traffic
- Top airports by cargo volume
- Top airports by aircraft movements
- International passenger rankings
- Key statistics and insights
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
import json
import re


# Ranking table images (PNG format - contain detailed Top 20 tables)
RANKING_IMAGES = {
    "total_passengers": {
        "url": "https://blog.aci.aero/wp-content/uploads/2025/07/image-3.png",
        "description": "Top 20 airports by total passenger traffic (2024)",
        "year": 2024
    },
    "cargo": {
        "url": "https://blog.aci.aero/wp-content/uploads/2025/07/image-1.png",
        "description": "Top 20 airports by cargo volume (2024)",
        "year": 2024
    },
    "aircraft_movements": {
        "url": "https://blog.aci.aero/wp-content/uploads/2025/07/image-2.png",
        "description": "Top 20 airports by aircraft movements (2024)",
        "year": 2024
    },
    "international_passengers": {
        "url": "https://blog.aci.aero/wp-content/uploads/2025/07/image-4.png",
        "description": "Top 20 airports by international passengers (2024)",
        "year": 2024
    }
}

# Known ranking data from ACI World 2024 report
KNOWN_RANKINGS = {
    "top_5_passengers_2024": [
        {"rank": 1, "airport": "Atlanta Hartsfield–Jackson International", "code": "ATL", "country": "United States"},
        {"rank": 2, "airport": "Dubai International", "code": "DXB", "country": "United Arab Emirates"},
        {"rank": 3, "airport": "Dallas/Fort Worth International", "code": "DFW", "country": "United States"},
        {"rank": 4, "airport": "London Heathrow", "code": "LHR", "country": "United Kingdom"},
        {"rank": 5, "airport": "Tokyo Haneda", "code": "HND", "country": "Japan"}
    ],
    "top_5_cargo_2024": [
        {"rank": 1, "airport": "Hong Kong International", "code": "HKG", "country": "Hong Kong"},
        {"rank": 2, "airport": "Shanghai Pudong International", "code": "PVG", "country": "China"},
        {"rank": 3, "airport": "Memphis International", "code": "MEM", "country": "United States"},
        {"rank": 4, "airport": "Ted Stevens Anchorage International", "code": "ANC", "country": "United States"},
        {"rank": 5, "airport": "Louisville Muhammad Ali International", "code": "SDF", "country": "United States"}
    ],
    "top_international_passengers": {
        "airport": "Dubai International",
        "code": "DXB",
        "note": "Global leader in international passenger traffic"
    }
}

# Key statistics from the 2024 report
KEY_STATISTICS = {
    "total_passengers_2024": {
        "value": 9.4e9,
        "unit": "passengers",
        "change_yoy": "+8.4%",
        "vs_2019": "+2.7%"
    },
    "total_cargo_2024": {
        "value": 127e6,
        "unit": "metric tonnes",
        "change_yoy": "+9.9%"
    },
    "total_movements_2024": {
        "value": 100.6e6,
        "unit": "aircraft movements",
        "change_yoy": "+3.9%",
        "vs_2019": "96.8%"
    },
    "airports_covered": 2800,
    "countries_covered": 185
}

# Notable highlights
NOTABLE_HIGHLIGHTS = [
    "Atlanta (ATL) maintains top position for consecutive years",
    "Shanghai Pudong (PVG) climbed 11 places into global top 10 for passengers",
    "Guangzhou Baiyun (CAN) ranked 12th (was 57th two years earlier)",
    "Dubai (DXB) jumped 6 places to 11th globally in air cargo volume",
    "Japan's Haneda and Narita posted strong international gains",
    "King Fahd International (DMM) remains largest airport by area",
    "North America leads in all three categories: passengers, cargo, movements"
]


async def fetch_article(url: str) -> dict:
    """Fetch and parse the ACI blog article."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    return {"error": f"HTTP {response.status}", "success": False}
                
                html = await response.text()
    except Exception as e:
        return {"error": str(e), "success": False}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else ""
    
    # Extract meta description
    meta = soup.find('meta', attrs={'name': 'description'})
    description = meta['content'] if meta else ""
    
    # Extract article content - try multiple selectors
    article = (
        soup.find('div', class_='post-content') or
        soup.find('div', class_='entry-content') or
        soup.find('article') or
        soup.find('main')
    )
    
    paragraphs = []
    if article:
        for p in article.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)
    
    # Extract JSON-LD metadata
    metadata = {}
    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            if isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'BlogPosting':
                        metadata = {
                            'headline': item.get('headline', ''),
                            'datePublished': item.get('datePublished', ''),
                            'dateModified': item.get('dateModified', ''),
                            'author': item.get('author', {}).get('name', ''),
                            'description': item.get('description', '')
                        }
        except:
            pass
    
    return {
        "title": title,
        "description": description,
        "paragraphs": paragraphs,
        "metadata": metadata,
        "success": True
    }


async def get_rankings_image_url(category: str) -> dict:
    """Get the URL for a ranking table image."""
    if category not in RANKING_IMAGES:
        return {
            "error": f"Unknown category: {category}. Valid categories: {list(RANKING_IMAGES.keys())}",
            "success": False
        }
    
    img_data = RANKING_IMAGES[category]
    return {
        "category": category,
        "url": img_data["url"],
        "description": img_data["description"],
        "year": img_data["year"],
        "success": True
    }


async def get_all_ranking_images() -> dict:
    """Get all ranking table image URLs."""
    return {
        "images": RANKING_IMAGES,
        "note": "These are PNG images containing detailed Top 20 ranking tables",
        "success": True
    }


async def get_airport_rankings(category: str = "all") -> dict:
    """
    Get known airport rankings.
    
    Args:
        category: "passengers", "cargo", "international", or "all"
    """
    result = {"success": True}
    
    if category in ["passengers", "all"]:
        result["top_5_passengers"] = KNOWN_RANKINGS["top_5_passengers_2024"]
    
    if category in ["cargo", "all"]:
        result["top_5_cargo"] = KNOWN_RANKINGS["top_5_cargo_2024"]
    
    if category in ["international", "all"]:
        result["top_international_passenger_airport"] = KNOWN_RANKINGS["top_international_passengers"]
    
    return result


async def get_statistics() -> dict:
    """Get key statistics from the 2024 report."""
    return {
        "statistics": KEY_STATISTICS,
        "highlights": NOTABLE_HIGHLIGHTS,
        "success": True
    }


async def search_airport(query: str) -> dict:
    """
    Search for an airport in the rankings.
    
    Args:
        query: Airport name, code, or country to search for
    """
    query_lower = query.lower()
    results = []
    
    # Search in passenger rankings
    for airport in KNOWN_RANKINGS["top_5_passengers_2024"]:
        if (query_lower in airport["airport"].lower() or 
            query_lower in airport["code"].lower() or 
            query_lower in airport["country"].lower()):
            results.append({
                **airport,
                "category": "total_passengers",
                "category_description": "Top airports by total passenger traffic"
            })
    
    # Search in cargo rankings
    for airport in KNOWN_RANKINGS["top_5_cargo_2024"]:
        if (query_lower in airport["airport"].lower() or 
            query_lower in airport["code"].lower() or 
            query_lower in airport["country"].lower()):
            results.append({
                **airport,
                "category": "cargo",
                "category_description": "Top airports by cargo volume"
            })
    
    # Check international leader
    intl = KNOWN_RANKINGS["top_international_passengers"]
    if (query_lower in intl["airport"].lower() or 
        query_lower in intl["code"].lower()):
        results.append({
            "rank": 1,
            "airport": intl["airport"],
            "code": intl["code"],
            "category": "international_passengers",
            "category_description": "Top airport by international passengers",
            "note": intl["note"]
        })
    
    if not results:
        return {
            "query": query,
            "results": [],
            "message": f"No airports found matching '{query}' in the Top 5 rankings",
            "success": True
        }
    
    return {
        "query": query,
        "results": results,
        "success": True
    }


async def get_article_content(url: str = None) -> dict:
    """Fetch and return the full article content."""
    target_url = url or "https://blog.aci.aero/airport-economics/busiest-airports-in-the-world-2024/"
    
    article = await fetch_article(target_url)
    
    if not article.get("success"):
        return article
    
    return {
        "url": target_url,
        "title": article.get("title", ""),
        "description": article.get("description", ""),
        "metadata": article.get("metadata", {}),
        "content": article.get("paragraphs", []),
        "ranking_images": RANKING_IMAGES,
        "dataset_link": "https://store.aci.aero/product/annual-world-airport-traffic-dataset-2025/",
        "success": True
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute ACI World airport rankings query.
    
    Args:
        params: Must contain 'function' key specifying the action
            - get_rankings: Get airport rankings (passengers, cargo, international)
            - get_statistics: Get key global statistics
            - get_article: Fetch the full article
            - get_ranking_tables: Get URLs for ranking table images
            - search_airport: Search for a specific airport
            - get_all: Get all available data
            
        Additional params:
            - category: For get_rankings (passengers/cargo/international/all)
            - url: For get_article (optional, uses default URL)
            - query: For search_airport (airport name/code/country)
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "available_functions": [
                "get_rankings",
                "get_statistics",
                "get_article",
                "get_ranking_tables",
                "search_airport",
                "get_all"
            ],
            "success": False
        }
    
    try:
        if function == "get_rankings":
            category = params.get("category", "all")
            return await get_airport_rankings(category)
        
        elif function == "get_statistics":
            return await get_statistics()
        
        elif function == "get_article":
            url = params.get("url")
            return await get_article_content(url)
        
        elif function == "get_ranking_tables":
            category = params.get("category")
            if category:
                return await get_rankings_image_url(category)
            else:
                return await get_all_ranking_images()
        
        elif function == "search_airport":
            query = params.get("query", "")
            if not query:
                return {
                    "error": "Missing required parameter: query (airport name/code/country)",
                    "success": False
                }
            return await search_airport(query)
        
        elif function == "get_all":
            article = await get_article_content()
            return {
                "article": {
                    "title": article.get("title"),
                    "url": article.get("url"),
                    "description": article.get("description"),
                    "metadata": article.get("metadata"),
                    "dataset_link": article.get("dataset_link")
                },
                "rankings": await get_airport_rankings("all"),
                "statistics": KEY_STATISTICS,
                "highlights": NOTABLE_HIGHLIGHTS,
                "ranking_table_images": RANKING_IMAGES,
                "success": True
            }
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_rankings",
                    "get_statistics",
                    "get_article",
                    "get_ranking_tables",
                    "search_airport",
                    "get_all"
                ],
                "success": False
            }
    
    except Exception as e:
        return {
            "error": f"Execution error: {str(e)}",
            "success": False
        }