"""
Recreation.gov Access Skill

Fetches facility data from Recreation.gov for:
- Ticket facilities (tours, timed entry)
- Site passes (park entrance passes) 
- Campgrounds (campsites, availability)
"""

import aiohttp
from typing import Any
from datetime import datetime


BASE_URL = "https://www.recreation.gov/api"

# Default headers to mimic browser requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.recreation.gov/",
}


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch JSON from URL with error handling"""
    try:
        async with session.get(url, headers=DEFAULT_HEADERS) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                return {
                    "error": f"HTTP {response.status}",
                    "url": url,
                    "message": text[:500]
                }
    except Exception as e:
        return {
            "error": "Request failed",
            "url": url,
            "message": str(e)
        }


async def _get_ticket_facility(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get ticket facility details"""
    url = f"{BASE_URL}/ticket/facility/{facility_id}"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    # Extract key info
    result = {
        "facility_id": facility_id,
        "name": data.get("facility_name", data.get("name", "")),
        "description": data.get("facility_description", ""),
        "facility_type": data.get("facility_type", ""),
        "enabled": data.get("enabled", False),
        "agency_name": data.get("agency_name", ""),
        "addresses": data.get("asset_addresses", []),
        "media": data.get("asset_media", [])[:5],  # Limit media
        "activities": data.get("asset_activities", []),
        "links": data.get("asset_links", []),
        "seasons": data.get("seasons", []),
        "city": data.get("city", ""),
        "state": data.get("state", ""),
        "latitude": data.get("facility_latitude"),
        "longitude": data.get("facility_longitude"),
        "phone": data.get("facility_phone", ""),
        "email": data.get("facility_email", ""),
        "raw": data
    }
    
    return result


async def _get_ticket_tours(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get tours for a ticket facility"""
    url = f"{BASE_URL}/ticket/facility/{facility_id}/tour"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    # Parse tours
    tours = []
    if isinstance(data, list):
        for tour in data:
            tours.append({
                "tour_id": tour.get("tour_id"),
                "name": tour.get("tour_name", ""),
                "description": tour.get("description", ""),
                "tour_type": tour.get("tour_type", ""),
                "duration": tour.get("tour_duration", ""),
                "distance": tour.get("distance", ""),
                "capacity": tour.get("tour_capacity", 0),
                "checked_in_count": tour.get("checked_in_count", 0),
                "sales_allowed": tour.get("sales_allowed", []),
                "apple_pass_active": tour.get("apple_pass_active", False),
            })
    
    return {
        "facility_id": facility_id,
        "total_tours": len(tours),
        "tours": tours,
        "raw": data
    }


async def _get_ticket_pricing(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get pricing for a ticket facility"""
    url = f"{BASE_URL}/ticket/facility/{facility_id}/pricing/view"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    # Extract pricing summary
    pricing = []
    by_category = data.get("tour_pricings_by_sales_category", {})
    
    for category, items in by_category.items():
        for item in items:
            tour_pricing = {
                "tour_id": item.get("tour_id"),
                "tour_name": item.get("tour_name", ""),
                "category": category,
                "cancellation_fee": item.get("cancellation_fee", {}),
                "late_cancellation_fee": item.get("late_cancellation_fee", {}),
                "cancellation_window_description": item.get("cancellation_window_description", ""),
                "guest_types": {}
            }
            
            guest_types = item.get("guest_type_pricing_by_guest_type_id", {})
            for guest_id, pricing_info in guest_types.items():
                tour_pricing["guest_types"][guest_id] = {
                    "ticket_cost": pricing_info.get("ticket_cost", 0),
                    "ticket_required": pricing_info.get("ticket_required", False),
                    "reservation_fee": pricing_info.get("reservation_fee", {})
                }
            
            pricing.append(tour_pricing)
    
    return {
        "facility_id": facility_id,
        "pricing": pricing,
        "raw": data
    }


async def _get_ticket_availability(session: aiohttp.ClientSession, facility_id: str, year: int, month: int) -> dict:
    """Get monthly availability summary for a ticket facility"""
    url = f"{BASE_URL}/ticket/availability/facility/{facility_id}/monthlyAvailabilitySummaryView"
    params = f"?year={year}&month={month:02d}&inventoryBucket=FIT"
    
    data = await _fetch_json(session, url + params)
    
    if "error" in data:
        return data
    
    # Parse availability summary
    availability = {}
    summary = data.get("facility_availability_summary_view_by_local_date", {})
    
    for date, info in summary.items():
        availability[date] = {
            "availability_level": info.get("availability_level", ""),
            "reserved_count": info.get("reserved_count", 0),
            "scheduled_count": info.get("scheduled_count", 0),
            "available_times": info.get("available_times", [])
        }
    
    return {
        "facility_id": facility_id,
        "year": year,
        "month": month,
        "availability": availability,
        "raw": data
    }


async def _get_campground(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get campground details"""
    url = f"{BASE_URL}/camps/campgrounds/{facility_id}"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    cg = data.get("campground", data)
    
    result = {
        "facility_id": facility_id,
        "name": cg.get("facility_name", ""),
        "facility_type": cg.get("facility_type", ""),
        "description": cg.get("facility_description_map", {}),
        "latitude": cg.get("facility_latitude"),
        "longitude": cg.get("facility_longitude"),
        "city": cg.get("city", ""),
        "state": cg.get("state", ""),
        "address": cg.get("facility_address", {}),
        "phone": cg.get("facility_phone", ""),
        "email": cg.get("facility_email", ""),
        "directions": cg.get("facility_directions", ""),
        "reservation_url": cg.get("facility_reservation_url", ""),
        "map_url": cg.get("facility_map_url", ""),
        "enabled": cg.get("enabled", False),
        "checkin_time": cg.get("checkin_time", ""),
        "checkout_time": cg.get("checkout_time", ""),
        "loop_count": cg.get("loop_count", 0),
        "num_campsites": cg.get("num_campsites", 0),
        "total_capacity": cg.get("total_capacity", 0),
        "seasons": cg.get("seasons", []),
        "raw": data
    }
    
    return result


async def _get_campsites(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get campsites for a campground"""
    url = f"{BASE_URL}/camps/campgrounds/{facility_id}/campsites"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    campsites = data.get("campsites", [])
    
    # Summarize campsites
    summary = []
    for site in campsites:
        summary.append({
            "campsite_id": site.get("campsite_id"),
            "name": site.get("campsite_name", ""),
            "type": site.get("campsite_type", ""),
            "loop": site.get("loop", ""),
            "accessible": site.get("is_accessible", False),
            "latitude": site.get("campsite_latitude"),
            "longitude": site.get("campsite_longitude"),
            "type_of_use": site.get("type_of_use", ""),
            "permitted_equipment": [e.get("equipment_name") for e in site.get("permitted_equipment", [])],
            "notices": [n.get("notice_text", "")[:100] for n in site.get("notices", [])[:3]]
        })
    
    return {
        "facility_id": facility_id,
        "total_sites": len(summary),
        "campsites": summary,
        "raw": data
    }


async def _get_sitepass_facility(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get sitepass/park pass facility details"""
    url = f"{BASE_URL}/parkpass/facilities/{facility_id}"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    facility = data.get("facility", data)
    
    result = {
        "facility_id": facility_id,
        "name": facility.get("name", ""),
        "agency": facility.get("agency", ""),
        "state": facility.get("state", ""),
        "facility_type": facility.get("facility_type", ""),
        "entrances": facility.get("entrances", []),
        "free_days": facility.get("free_days", []),
        "blackout_periods": facility.get("blackout_periods", []),
        "contents": facility.get("contents", {}),
        "latitude": facility.get("lat_long", {}).get("lat"),
        "longitude": facility.get("lat_long", {}).get("long"),
        "active_on": facility.get("active_on", ""),
        "raw": data
    }
    
    return result


async def _get_sitepass_types(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get pass types for a sitepass facility"""
    url = f"{BASE_URL}/parkpass/passtypes/facility/{facility_id}"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    pass_types = data.get("pass_types", [])
    
    # Summarize pass types
    summary = []
    for pt in pass_types:
        pricing = []
        for period in pt.get("periods", []):
            for div in period.get("divisions", []):
                pricing.append({
                    "start_date": period.get("start_date"),
                    "name": div.get("name"),
                    "display_price": div.get("display_price"),
                    "price": div.get("price", 0) / 100000  # Price appears to be in micros
                })
        
        summary.append({
            "pass_type_id": pt.get("id"),
            "name": pt.get("name", ""),
            "duration": pt.get("duration", ""),
            "transportation_type": pt.get("transportation_type_name", ""),
            "sku": pt.get("sku", ""),
            "used_for": pt.get("used_for", ""),
            "pricing": pricing
        })
    
    return {
        "facility_id": facility_id,
        "total_pass_types": len(summary),
        "pass_types": summary,
        "raw": data
    }


async def _get_facility_search(session: aiohttp.ClientSession, facility_id: str) -> dict:
    """Get facility info via search API"""
    url = f"{BASE_URL}/search?fq=entity_id:{facility_id}"
    data = await _fetch_json(session, url)
    
    if "error" in data:
        return data
    
    return {
        "facility_id": facility_id,
        "search_result": data
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Recreation.gov API calls
    
    Parameters:
        function: One of:
            - get_ticket_facility: Get ticket facility details
            - get_ticket_tours: Get tours for a ticket facility
            - get_ticket_pricing: Get pricing for a ticket facility
            - get_ticket_availability: Get monthly availability for tickets
            - get_campground: Get campground details
            - get_campsites: Get campsites for a campground
            - get_sitepass_facility: Get sitepass/park pass facility details
            - get_sitepass_types: Get pass types for a sitepass facility
            - get_facility_search: Get facility info via search API
        
        facility_id: The facility ID (required for all functions)
        year: Year for availability queries (optional, defaults to current year)
        month: Month for availability queries (optional, defaults to current month)
    """
    function = params.get("function")
    facility_id = params.get("facility_id")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    if not facility_id:
        return {"error": "Missing required parameter: facility_id"}
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == "get_ticket_facility":
                return await _get_ticket_facility(session, facility_id)
            
            elif function == "get_ticket_tours":
                return await _get_ticket_tours(session, facility_id)
            
            elif function == "get_ticket_pricing":
                return await _get_ticket_pricing(session, facility_id)
            
            elif function == "get_ticket_availability":
                # Get year and month, defaulting to current
                now = datetime.now()
                year = params.get("year", now.year)
                month = params.get("month", now.month)
                return await _get_ticket_availability(session, facility_id, year, month)
            
            elif function == "get_campground":
                return await _get_campground(session, facility_id)
            
            elif function == "get_campsites":
                return await _get_campsites(session, facility_id)
            
            elif function == "get_sitepass_facility":
                return await _get_sitepass_facility(session, facility_id)
            
            elif function == "get_sitepass_types":
                return await _get_sitepass_types(session, facility_id)
            
            elif function == "get_facility_search":
                return await _get_facility_search(session, facility_id)
            
            else:
                return {"error": f"Unknown function: {function}"}
                
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test ticket facility
        print("=" * 80)
        print("Testing Ticket Facility")
        print("=" * 80)
        result = await execute({"function": "get_ticket_facility", "facility_id": "233362"})
        print(f"Name: {result.get('name', result.get('error', 'Unknown'))}")
        
        # Test campground
        print("\n" + "=" * 80)
        print("Testing Campground")
        print("=" * 80)
        result = await execute({"function": "get_campground", "facility_id": "232446"})
        print(f"Name: {result.get('name', result.get('error', 'Unknown'))}")
        print(f"Total sites: {result.get('num_campsites', 'N/A')}")
        
        # Test sitepass
        print("\n" + "=" * 80)
        print("Testing Sitepass")
        print("=" * 80)
        result = await execute({"function": "get_sitepass_facility", "facility_id": "72144"})
        print(f"Name: {result.get('name', result.get('error', 'Unknown'))}")
        print(f"Agency: {result.get('agency', 'N/A')}")
    
    asyncio.run(test())