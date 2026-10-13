"""
Michelin Guide Restaurant Search Skill

This skill provides access to the Michelin Guide restaurant database via Algolia API.
It allows searching for restaurants by name, location, distinction (stars), and other criteria.
"""

import asyncio
import aiohttp
from typing import Any, Optional
from urllib.parse import quote


# Algolia configuration
ALGOLIA_APP_ID = "8NVHRD7ONV"
ALGOLIA_API_KEY = "3222e669cf890dc73fa5f38241117ba5"
ALGOLIA_INDEX = "prod-restaurants-en"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/*/queries"

# Headers required for Algolia API
ALGOLIA_HEADERS = {
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "X-Algolia-Agent": "Algolia for JavaScript (5.47.0); Browser",
    "Content-Type": "application/json",
    "Origin": "https://guide.michelin.com",
    "Referer": "https://guide.michelin.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# Distinction/award slugs
DISTINCTION_SLUGS = {
    "3-stars": "3-stars-michelin",
    "3-star": "3-stars-michelin",
    "three-stars": "3-stars-michelin",
    "three-star": "3-stars-michelin",
    "2-stars": "2-stars-michelin",
    "2-star": "2-stars-michelin",
    "two-stars": "2-stars-michelin",
    "two-star": "2-stars-michelin",
    "1-star": "1-star-michelin",
    "one-star": "1-star-michelin",
    "bib-gourmand": "bib-gourmand",
    "bib": "bib-gourmand",
    "plate": "the-plate-michelin",
    "michelin-plate": "the-plate-michelin",
}

# Distinction display names
DISTINCTION_NAMES = {
    "3-stars-michelin": "3 Stars MICHELIN",
    "2-stars-michelin": "2 Stars MICHELIN",
    "1-star-michelin": "1 Star MICHELIN",
    "bib-gourmand": "Bib Gourmand",
    "the-plate-michelin": "The Plate MICHELIN",
}


def normalize_distinction(distinction: str) -> Optional[str]:
    """Normalize distinction input to slug format."""
    if not distinction:
        return None
    distinction_lower = distinction.lower().strip()
    
    # Check direct mapping
    if distinction_lower in DISTINCTION_SLUGS:
        return DISTINCTION_SLUGS[distinction_lower]
    
    # Check if it's already a valid slug
    if distinction_lower in DISTINCTION_NAMES:
        return distinction_lower
    
    # Check if it contains star pattern
    if "3" in distinction and "star" in distinction:
        return "3-stars-michelin"
    if "2" in distinction and "star" in distinction:
        return "2-stars-michelin"
    if "1" in distinction and "star" in distinction:
        return "1-star-michelin"
    
    return None


def format_restaurant(hit: dict) -> dict:
    """Format a restaurant hit from Algolia into a clean structured response."""
    
    distinction = hit.get("distinction", {})
    distinction_slug = distinction.get("slug", "") if distinction else ""
    
    # Get cuisines
    cuisines = hit.get("cuisines", [])
    cuisine_list = [c.get("label", "") for c in cuisines if c.get("label")]
    
    # Get images
    images = hit.get("images", [])
    main_image = hit.get("main_image", {}) or hit.get("image", "")
    
    # Get location
    city = hit.get("city", {})
    country = hit.get("country", {})
    region = hit.get("region", {})
    
    # Get price info
    price = hit.get("price", {})
    price_category = hit.get("price_category", {})
    
    # Build address
    address_parts = []
    if hit.get("street"):
        address_parts.append(hit["street"])
    if city and city.get("name"):
        address_parts.append(city["name"])
    if hit.get("postcode"):
        address_parts.append(hit["postcode"])
    if country and country.get("name"):
        address_parts.append(country["name"])
    
    # Get hours
    hours = hit.get("hours_of_operation", {})
    
    return {
        "id": hit.get("identifier"),
        "name": hit.get("name"),
        "slug": hit.get("slug"),
        "url": f"https://guide.michelin.com{hit.get('url', '')}",
        "short_link": hit.get("short_link"),
        
        # Distinction/Award
        "michelin_award": hit.get("michelin_award"),
        "michelin_star": hit.get("michelin_star"),
        "distinction": {
            "label": distinction.get("label"),
            "slug": distinction_slug,
            "display_name": DISTINCTION_NAMES.get(distinction_slug, distinction.get("label", ""))
        },
        "guide_year": hit.get("guide_year"),
        
        # Location
        "location": {
            "address": hit.get("street"),
            "city": city.get("name") if city else None,
            "city_slug": city.get("slug") if city else None,
            "region": region.get("name") if region else None,
            "region_slug": region.get("slug") if region else None,
            "country": country.get("name") if country else None,
            "country_code": country.get("code") if country else None,
            "country_slug": country.get("slug") if country else None,
            "postcode": hit.get("postcode"),
            "full_address": ", ".join(address_parts) if address_parts else None,
            "coordinates": hit.get("_geoloc"),
        },
        
        # Cuisine
        "cuisines": cuisine_list,
        "cuisines_detailed": cuisines,
        
        # Contact
        "phone": hit.get("phone"),
        "website": hit.get("website"),
        
        # Price
        "price": {
            "low": price.get("low") if price else None,
            "high": price.get("high") if price else None,
            "category": price_category.get("label") if price_category else None,
            "category_slug": price_category.get("slug") if price_category else None,
            "currency": hit.get("currency"),
            "currency_symbol": hit.get("currency_symbol"),
        },
        
        # Images
        "main_image": main_image.get("url") if isinstance(main_image, dict) else main_image,
        "images": [
            {
                "url": img.get("url"),
                "copyright": img.get("copyright"),
                "topic": img.get("topic"),
            }
            for img in images[:10]  # Limit to first 10 images
        ] if images else [],
        
        # Chef
        "chef": hit.get("chef"),
        
        # Booking
        "booking": {
            "available": hit.get("online_booking") == 1,
            "provider": hit.get("booking_provider"),
            "url": hit.get("booking_url"),
        },
        
        # Facilities & Services
        "facilities": hit.get("facilities", []),
        "take_away": hit.get("take_away") == 1,
        "delivery": hit.get("delivery") == 1,
        "good_menu": hit.get("good_menu") == 1,
        "green_star": hit.get("green_star"),
        
        # Special features
        "special_diets": hit.get("special_diets", []),
        "tags": hit.get("tag_thematic", []),
        
        # Hours
        "hours": hours if hours else None,
        
        # Description
        "description": hit.get("main_desc"),
    }


async def algolia_search(
    session: aiohttp.ClientSession,
    query: str = "",
    filters: str = "status:Published",
    facet_filters: list = None,
    optional_filters: list = None,
    around_lat_lng: str = None,
    around_radius: int = None,
    hits_per_page: int = 20,
    page: int = 0,
) -> dict:
    """Execute a search against Algolia."""
    
    request_body = {
        "indexName": ALGOLIA_INDEX,
        "query": query,
        "filters": filters,
        "hitsPerPage": hits_per_page,
        "page": page,
    }
    
    if facet_filters:
        request_body["facetFilters"] = facet_filters
    
    if optional_filters:
        request_body["optionalFilters"] = optional_filters
    
    if around_lat_lng:
        request_body["aroundLatLng"] = around_lat_lng
        request_body["aroundLatLngViaIP"] = False
        if around_radius:
            request_body["aroundRadius"] = around_radius
    
    params = {"requests": [request_body]}
    
    try:
        async with session.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {
                    "error": f"Algolia API error: {resp.status}",
                    "details": text[:500],
                    "success": False
                }
            
            data = await resp.json()
            results = data.get("results", [])
            
            if not results:
                return {
                    "error": "No results from Algolia",
                    "success": False
                }
            
            return {
                "result": results[0],
                "success": True
            }
    
    except aiohttp.ClientError as e:
        return {
            "error": f"Network error: {str(e)}",
            "success": False
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "success": False
        }


async def search_restaurants(params: dict, ctx: Any = None) -> dict:
    """
    Search for restaurants by name or other criteria.
    
    Parameters:
        - query: Search query (restaurant name, chef name, etc.)
        - city: City name (e.g., "Paris", "New York")
        - country: Country name or code (e.g., "France", "FR")
        - distinction: Michelin distinction (e.g., "3-stars", "bib-gourmand", "1-star")
        - cuisine: Cuisine type (e.g., "French", "Japanese", "Italian")
        - page: Page number (default 0)
        - limit: Number of results per page (default 20, max 100)
    """
    
    query = params.get("query", "").strip()
    city = params.get("city", "").strip().lower()
    country = params.get("country", "").strip().lower()
    distinction = params.get("distinction", "").strip()
    cuisine = params.get("cuisine", "").strip().lower()
    page = int(params.get("page", 0))
    limit = min(int(params.get("limit", 20)), 100)
    
    facet_filters = []
    optional_filters = []
    filters = ["status:Published"]
    
    # Add distinction filter
    if distinction:
        dist_slug = normalize_distinction(distinction)
        if dist_slug:
            facet_filters.append([f"distinction.slug:{dist_slug}"])
    
    # Add green star if specified
    if params.get("green_star"):
        facet_filters.append(["green_star.slug:green-star"])
    
    # Build optional filters for city/country
    if city:
        optional_filters.append(f"city.slug:{city.replace(' ', '-')}")
    
    if country:
        # Try both slug and name
        optional_filters.append(f"country.slug:{country}")
    
    # Add cuisine filter
    if cuisine:
        facet_filters.append([f"cuisines.slug:{cuisine.replace(' ', '-')}"])
    
    async with aiohttp.ClientSession() as session:
        result = await algolia_search(
            session,
            query=query,
            filters=" AND ".join(filters),
            facet_filters=facet_filters if facet_filters else None,
            optional_filters=optional_filters if optional_filters else None,
            hits_per_page=limit,
            page=page,
        )
        
        if not result.get("success"):
            return result
        
        search_result = result["result"]
        hits = search_result.get("hits", [])
        
        return {
            "success": True,
            "total_hits": search_result.get("nbHits", 0),
            "page": search_result.get("page", 0),
            "total_pages": search_result.get("nbPages", 0),
            "hits_per_page": search_result.get("hitsPerPage", limit),
            "query": query,
            "filters_applied": {
                "city": city if city else None,
                "country": country if country else None,
                "distinction": distinction if distinction else None,
                "cuisine": cuisine if cuisine else None,
            },
            "restaurants": [format_restaurant(hit) for hit in hits],
        }


async def get_restaurant_by_slug(params: dict, ctx: Any = None) -> dict:
    """
    Get detailed information about a specific restaurant by its slug.
    
    Parameters:
        - slug: Restaurant slug (e.g., "epicure", "le-gabriel476630")
    """
    
    slug = params.get("slug", "").strip()
    
    if not slug:
        return {
            "error": "Missing required parameter: slug",
            "success": False
        }
    
    # Clean slug if it contains URL path
    if "/" in slug:
        slug = slug.split("/")[-1]
    
    async with aiohttp.ClientSession() as session:
        result = await algolia_search(
            session,
            query="",
            filters=f"slug:{slug} AND status:Published",
            hits_per_page=1,
        )
        
        if not result.get("success"):
            return result
        
        hits = result["result"].get("hits", [])
        
        if not hits:
            return {
                "error": f"Restaurant not found with slug: {slug}",
                "success": False
            }
        
        return {
            "success": True,
            "restaurant": format_restaurant(hits[0]),
        }


async def get_restaurants_by_location(params: dict, ctx: Any = None) -> dict:
    """
    Search for restaurants near a geographic location.
    
    Parameters:
        - lat: Latitude (e.g., 48.8566)
        - lng: Longitude (e.g., 2.3522)
        - radius: Search radius in meters (default 5000)
        - distinction: Optional Michelin distinction filter
        - limit: Number of results (default 20, max 100)
        - page: Page number (default 0)
    """
    
    try:
        lat = float(params.get("lat", 0))
        lng = float(params.get("lng", 0))
    except (ValueError, TypeError):
        return {
            "error": "Invalid latitude or longitude",
            "success": False
        }
    
    if not lat or not lng:
        return {
            "error": "Missing required parameters: lat and lng",
            "success": False
        }
    
    radius = int(params.get("radius", 5000))
    distinction = params.get("distinction", "").strip()
    limit = min(int(params.get("limit", 20)), 100)
    page = int(params.get("page", 0))
    
    facet_filters = []
    
    if distinction:
        dist_slug = normalize_distinction(distinction)
        if dist_slug:
            facet_filters.append([f"distinction.slug:{dist_slug}"])
    
    async with aiohttp.ClientSession() as session:
        result = await algolia_search(
            session,
            query="",
            filters="status:Published",
            facet_filters=facet_filters if facet_filters else None,
            around_lat_lng=f"{lat},{lng}",
            around_radius=radius,
            hits_per_page=limit,
            page=page,
        )
        
        if not result.get("success"):
            return result
        
        search_result = result["result"]
        hits = search_result.get("hits", [])
        
        return {
            "success": True,
            "total_hits": search_result.get("nbHits", 0),
            "page": search_result.get("page", 0),
            "total_pages": search_result.get("nbPages", 0),
            "location": {
                "lat": lat,
                "lng": lng,
                "radius_meters": radius,
            },
            "distinction_filter": distinction if distinction else None,
            "restaurants": [format_restaurant(hit) for hit in hits],
        }


async def get_available_filters(params: dict, ctx: Any = None) -> dict:
    """
    Get available filter options (distinctions, cuisines, etc.)
    """
    
    async with aiohttp.ClientSession() as session:
        request_body = {
            "indexName": ALGOLIA_INDEX,
            "query": "",
            "filters": "status:Published",
            "hitsPerPage": 0,
            "facets": [
                "distinction.slug",
                "cuisines.slug",
                "price_category.slug",
            ],
            "maxValuesPerFacet": 200,
        }
        
        params_data = {"requests": [request_body]}
        
        try:
            async with session.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=params_data) as resp:
                if resp.status != 200:
                    return {
                        "error": f"API error: {resp.status}",
                        "success": False
                    }
                
                data = await resp.json()
                facets = data["results"][0].get("facets", {})
                
                distinctions = sorted(
                    [
                        {
                            "slug": k,
                            "count": v,
                            "display_name": DISTINCTION_NAMES.get(k, k)
                        }
                        for k, v in facets.get("distinction.slug", {}).items()
                    ],
                    key=lambda x: -x["count"]
                )
                
                cuisines = sorted(
                    [
                        {"slug": k, "count": v}
                        for k, v in facets.get("cuisines.slug", {}).items()
                    ],
                    key=lambda x: (-x["count"], x["slug"])
                )
                
                price_categories = sorted(
                    [
                        {"slug": k, "count": v}
                        for k, v in facets.get("price_category.slug", {}).items()
                    ],
                    key=lambda x: -x["count"]
                )
                
                return {
                    "success": True,
                    "distinctions": distinctions,
                    "cuisines": cuisines[:50],  # Top 50 cuisines
                    "price_categories": price_categories,
                }
        
        except Exception as e:
            return {
                "error": f"Error: {str(e)}",
                "success": False
            }


async def execute(params: dict, ctx: Any = None) -> dict:
    """
    Main entry point for the Michelin Guide skill.
    
    Supported functions:
        - search: Search for restaurants by name, location, distinction, etc.
        - get_by_slug: Get a specific restaurant by its slug
        - search_by_location: Search for restaurants near coordinates
        - get_filters: Get available filter options
    
    Parameters:
        - function: The function to execute ("search", "get_by_slug", "search_by_location", "get_filters")
        - ... additional parameters based on function
    """
    
    function = params.get("function", "search")
    
    if function == "search":
        return await search_restaurants(params, ctx)
    elif function == "get_by_slug":
        return await get_restaurant_by_slug(params, ctx)
    elif function == "search_by_location":
        return await get_restaurants_by_location(params, ctx)
    elif function == "get_filters":
        return await get_available_filters(params, ctx)
    else:
        return {
            "error": f"Unknown function: {function}. Supported functions: search, get_by_slug, search_by_location, get_filters",
            "success": False
        }