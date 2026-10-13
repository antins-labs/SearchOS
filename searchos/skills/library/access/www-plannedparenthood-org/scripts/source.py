"""
Planned Parenthood Health Center Access Skill

Fetches health center information from Planned Parenthood's public API including:
- Search health centers by location (zip, city, state)
- Filter by service type (abortion, birth-control, std-testing, etc.)
- Filter by channel (telehealth, onsite)
- Get real-time opening hours for facilities
"""

import asyncio
import aiohttp
from typing import Any, Optional
from urllib.parse import urlencode


BASE_URL = "https://www.plannedparenthood.org"

# Known service slugs for validation
SERVICE_SLUGS = {
    "abortion",
    "birth-control",
    "emergency-contraception",
    "std-testing",
    "hiv-testing",
    "gender-affirming-care",
    "pregnancy-testing",
    "prenatal-postpartum",
    "sexual-reproductive",
    "vaccines",
    "wellness-preventive",
    "mental-health",
}

SERVICE_IDS = {
    "abortionservice",
    "birthcontrolservice",
    "emergencycontraceptionservice",
    "stdservice",
    "hivtestingservice",
    "lgbtservice",
    "pregnancyservice",
    "prenatalpostpartumservice",
    "sexualhealthservice",
    "vaccinesservice",
    "generalhealthservice",
    "mentalhealthservice",
}

CHANNEL_VALUES = {"telehealth", "onsite", "ppdirect"}


async def _make_request(
    session: aiohttp.ClientSession, url: str, params: Optional[dict] = None
) -> dict:
    """Make an HTTP GET request and return JSON response."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{BASE_URL}/health-center",
    }

    full_url = f"{url}?{urlencode(params)}" if params else url

    try:
        async with session.get(full_url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                return {
                    "error": True,
                    "status_code": resp.status,
                    "message": f"HTTP {resp.status}: {text[:500]}",
                }
            return await resp.json()
    except Exception as e:
        return {"error": True, "message": f"Request failed: {str(e)}"}


async def search_health_centers(
    location: str,
    service: Optional[str] = None,
    channel: Optional[str] = None,
    distance: Optional[int] = None,
    page: int = 1,
) -> dict:
    """
    Search for Planned Parenthood health centers.

    Args:
        location: Zip code, city name, or state name (required)
        service: Filter by service type (e.g., 'abortion', 'birth-control')
        channel: Filter by channel ('telehealth', 'onsite', 'ppdirect')
        distance: Maximum distance in miles
        page: Page number for pagination (default 1)

    Returns:
        Dict with count, results list, and pagination info
    """
    params = {
        "location": location,
        "service": service or "",
        "channel": channel or "",
        "distance": str(distance) if distance else "",
        "page": page,
    }

    async with aiohttp.ClientSession() as session:
        # Validate location first
        validate_url = f"{BASE_URL}/health-center/api/_validate_location"
        validate_result = await _make_request(
            session, validate_url, {"location": location}
        )

        if validate_result.get("error"):
            return validate_result

        if not validate_result.get("valid"):
            return {
                "error": True,
                "message": f"Invalid location: {location}",
                "validation": validate_result,
            }

        # Perform search
        search_url = f"{BASE_URL}/health-center/api/search"
        result = await _make_request(session, search_url, params)

        if result.get("error"):
            return result

        # Enrich results
        enriched = {
            "count": result.get("count"),
            "page": page,
            "location_type": validate_result.get("search_type"),
            "results": result.get("results", []),
        }

        if result.get("next"):
            enriched["next_page"] = page + 1
        if result.get("previous"):
            enriched["previous_page"] = page - 1 if page > 1 else None

        return enriched


async def get_opening_hours(facility_ids: list[int]) -> dict:
    """
    Get real-time opening hours for facilities.

    Args:
        facility_ids: List of facility IDs

    Returns:
        Dict with hours data for each facility
    """
    if not facility_ids:
        return {"error": True, "message": "No facility IDs provided"}

    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/_facility-opening-hours"
        params = {"facility_ids": ",".join(str(fid) for fid in facility_ids)}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{BASE_URL}/health-center",
        }

        full_url = f"{url}?{urlencode(params)}"

        try:
            async with session.get(full_url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "error": True,
                        "status_code": resp.status,
                        "message": f"HTTP {resp.status}: {text[:500]}",
                    }
                data = await resp.json()
                # API returns a list directly
                if isinstance(data, list):
                    return {"facilities": data}
                return data
        except Exception as e:
            return {"error": True, "message": f"Request failed: {str(e)}"}


async def get_services_list() -> dict:
    """
    Get list of known service types available at Planned Parenthood health centers.

    Returns:
        Dict with service slugs and their full names
    """
    return {
        "services": [
            {"slug": "abortion", "name": "Abortion", "id": "abortionservice"},
            {
                "slug": "birth-control",
                "name": "Birth Control",
                "id": "birthcontrolservice",
            },
            {
                "slug": "emergency-contraception",
                "name": "Emergency Contraception (Morning-After Pill)",
                "id": "emergencycontraceptionservice",
            },
            {
                "slug": "std-testing",
                "name": "STD Testing and Treatment",
                "id": "stdservice",
            },
            {"slug": "hiv-testing", "name": "HIV Services", "id": "hivtestingservice"},
            {
                "slug": "gender-affirming-care",
                "name": "Gender-Affirming Care",
                "id": "lgbtservice",
            },
            {
                "slug": "pregnancy-testing",
                "name": "Pregnancy Testing and Planning",
                "id": "pregnancyservice",
            },
            {
                "slug": "prenatal-postpartum",
                "name": "Prenatal and Postpartum Services",
                "id": "prenatalpostpartumservice",
            },
            {
                "slug": "sexual-reproductive",
                "name": "Sexual and Reproductive Concerns",
                "id": "sexualhealthservice",
            },
            {"slug": "vaccines", "name": "Vaccines", "id": "vaccinesservice"},
            {
                "slug": "wellness-preventive",
                "name": "Wellness and Preventive Care",
                "id": "generalhealthservice",
            },
            {"slug": "mental-health", "name": "Mental Health", "id": "mentalhealthservice"},
        ]
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Planned Parenthood health center queries.

    Dispatches based on params['function']:
        - search: Search health centers by location
        - hours: Get opening hours for facilities
        - services: List available service types
    """
    function = params.get("function")

    if not function:
        return {"error": True, "message": "Missing required parameter: function"}

    if function == "search":
        location = params.get("location")
        if not location:
            return {"error": True, "message": "Missing required parameter: location"}

        service = params.get("service")
        if service and service not in SERVICE_SLUGS:
            # Allow both slugs and service IDs
            if service not in SERVICE_IDS:
                return {
                    "error": True,
                    "message": f"Invalid service: {service}. Use get_services to see available options.",
                }

        channel = params.get("channel")
        if channel and channel not in CHANNEL_VALUES:
            return {
                "error": True,
                "message": f"Invalid channel: {channel}. Must be one of: {CHANNEL_VALUES}",
            }

        distance = params.get("distance")
        if distance is not None:
            try:
                distance = int(distance)
            except (ValueError, TypeError):
                return {"error": True, "message": "distance must be an integer"}

        page = params.get("page", 1)
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1

        return await search_health_centers(
            location=location,
            service=service,
            channel=channel,
            distance=distance,
            page=page,
        )

    elif function == "hours":
        facility_ids = params.get("facility_ids")
        if not facility_ids:
            return {"error": True, "message": "Missing required parameter: facility_ids"}

        if isinstance(facility_ids, str):
            # Allow comma-separated string
            try:
                facility_ids = [int(x.strip()) for x in facility_ids.split(",")]
            except ValueError:
                return {
                    "error": True,
                    "message": "facility_ids must be a list of integers or comma-separated string",
                }
        elif not isinstance(facility_ids, list):
            return {
                "error": True,
                "message": "facility_ids must be a list of integers or comma-separated string",
            }

        return await get_opening_hours(facility_ids)

    elif function == "services":
        return await get_services_list()

    else:
        return {
            "error": True,
            "message": f"Unknown function: {function}. Available: search, hours, services",
        }