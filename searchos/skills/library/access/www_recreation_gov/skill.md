# Recreation.gov Access Skill

Access structured facility data from Recreation.gov, the official booking platform for US federal lands including National Parks, National Forests, and other federal recreation sites.

## Overview

This skill provides direct API access to Recreation.gov's backend services, enabling you to retrieve:
- **Ticket facilities**: Tour details, pricing, and time-slot availability for attractions like Alcatraz, Mesa Verde cliff dwellings, etc.
- **Campgrounds**: Site details, amenities, campsite listings, and booking information
- **Site passes**: Park entrance pass options, pricing, and free day schedules

## Facility Types

### Ticket Facilities
Used for timed-entry tours and attractions. Examples:
- Mesa Verde National Park cliff dwelling tours
- Alcatraz Island tours
- Washington Monument tickets

### Campgrounds
Overnight camping facilities with reservable sites. Examples:
- Wawona Campground (Yosemite)
- Upper Pines Campground (Yosemite)
- Campgrounds across National Parks and Forests

### Site Passes
Digital entrance passes for parks and recreational areas. Examples:
- Great Sand Dunes National Park entrance pass
- National park entrance fees

## Facility IDs

Each facility on Recreation.gov has a unique numeric ID found in its URL:
- Ticket: `https://www.recreation.gov/ticket/facility/{facility_id}`
- Campground: `https://www.recreation.gov/camping/campgrounds/{facility_id}`
- Site Pass: `https://www.recreation.gov/sitepass/{facility_id}`

## Examples

### Get Ticket Facility Details

```python
result = await execute({
    "function": "get_ticket_facility",
    "facility_id": "233362"  # Mesa Verde National Park tours
})
# Returns: facility name, description, addresses, seasons, contact info
```

### Get Tour Availability

```python
result = await execute({
    "function": "get_ticket_availability",
    "facility_id": "233362",
    "year": 2026,
    "month": 6
})
# Returns: daily availability levels, reserved counts, available time slots
```

### Get Campground Information

```python
result = await execute({
    "function": "get_campground",
    "facility_id": "232446"  # Wawona Campground, Yosemite
})
# Returns: campground details, check-in/out times, descriptions, amenities
```

### Get Campsites List

```python
result = await execute({
    "function": "get_campsites",
    "facility_id": "232446"
})
# Returns: list of all campsites with names, types, equipment allowed, accessibility
```

### Get Park Pass Options

```python
result = await execute({
    "function": "get_sitepass_types",
    "facility_id": "72144"  # Great Sand Dunes National Park
})
# Returns: available pass types (vehicle, motorcycle, pedestrian), durations, pricing
```

## Response Structure

All responses follow a consistent pattern:
- **Summary fields**: Extracted key information (name, description, counts, etc.)
- **`raw` field**: Complete original API response for detailed analysis

### Example: Ticket Facility Response

```json
{
  "facility_id": "233362",
  "name": "Mesa Verde National Park Tours",
  "description": "...",
  "agency_name": "NPS",
  "addresses": [...],
  "seasons": [...],
  "raw": { /* complete API response */ }
}
```

### Example: Campsite Response

```json
{
  "facility_id": "232446",
  "total_sites": 93,
  "campsites": [
    {
      "campsite_id": "62",
      "name": "045",
      "type": "WALK TO",
      "loop": "C",
      "accessible": false,
      "permitted_equipment": ["Tent", "Small Tent"]
    },
    ...
  ]
}
```

## Notes

### Data Freshness
- Availability data is real-time from Recreation.gov's API
- Ticket availability shows current booking status with reserved/scheduled counts
- Campground data reflects the live database

### Rate Limiting
The Recreation.gov API is public but unofficial. The skill includes standard browser headers to ensure reliable access. For high-volume usage, consider implementing delays between requests.

### Availability Calendar
For ticket facilities, use `get_ticket_availability` with year and month parameters to see availability across different dates. Availability levels include:
- `HIGH`: Plenty of availability
- `MEDIUM`: Some availability
- `LOW`: Limited availability

### Free Days
Site pass facilities include `free_days` showing dates when entrance fees are waived (e.g., National Public Lands Day, Veterans Day).

## Data Sources

This skill accesses Recreation.gov's public API endpoints directly:
- `/api/ticket/facility/{id}` - Ticket facility details
- `/api/ticket/facility/{id}/tour` - Tour listings
- `/api/ticket/facility/{id}/pricing/view` - Pricing tiers
- `/api/ticket/availability/facility/{id}/monthlyAvailabilitySummaryView` - Calendar availability
- `/api/camps/campgrounds/{id}` - Campground details
- `/api/camps/campgrounds/{id}/campsites` - Campsite listings
- `/api/parkpass/facilities/{id}` - Site pass facility info
- `/api/parkpass/passtypes/facility/{id}` - Pass types and pricing

All data is officially sourced from the Recreation.gov platform operated by the US Department of the Interior.