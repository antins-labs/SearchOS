# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Viking Cruises Access Skill

This skill extracts cruise itinerary details, pricing, and sailing information from Viking Cruises website (vikingcruises.com).

## Features

- **get_cruise_details**: Retrieve comprehensive cruise itinerary information including:
  - Cruise name and description
  - Duration (days)
  - Number of guided tours included
  - Countries visited
  - Complete day-by-day itinerary with port information
  - Starting price

- **get_pricing**: Retrieve pricing and departure information including:
  - Available sailing dates for a specified year
  - Cruise fares and air fares for each departure
  - Starting/ending ports for each sailing
  - Current promotions and special offers
  - Starting from price

- **search_cruises**: Basic search functionality returning information about known cruise routes

## Usage Examples

### Get Cruise Details

```python
# Using individual parameters
result = await execute({
    "function": "get_cruise_details",
    "cruise_name": "alaska-inside-passage",
    "region": "caribbean-americas",
    "start_location": "vancouver-british-columbia",
    "end_location": "seward",
    "year": "2028"
}, ctx)

# Or using a full URL
result = await execute({
    "function": "get_cruise_details",
    "url": "https://www.vikingcruises.com/oceans/cruise-destinations/caribbean-americas/alaska-inside-passage/index.html?startLocation=vancouver-british-columbia&endLocation=seward&year=2028"
}, ctx)
```

### Get Pricing Information

```python
result = await execute({
    "function": "get_pricing",
    "cruise_name": "alaska-inside-passage",
    "region": "caribbean-americas",
    "start_location": "vancouver-british-columbia",
    "end_location": "seward",
    "year": "2028"
}, ctx)
```

## Sample Output

### Cruise Details Response

```json
{
  "success": true,
  "name": "Alaska & the Inside Passage",
  "description": "Immerse yourself in a world of Tlingit heritage...",
  "duration_days": 11,
  "guided_tours": 7,
  "countries": 2,
  "starting_price": "$5,999",
  "itinerary": [
    {"day": 1, "port_name": "Vancouver British Columbia", "port_id": "vancouver-british-columbia_van"},
    {"day": 2, "port_name": "Scenic Sailing The Inside Passage", "port_id": "scenic-sailing-the-inside-passage_672"},
    {"day": 3, "port_name": "Ketchikan Alaska", "port_id": "ketchikan-alaska_ktn"},
    ...
  ],
  "ports": ["Vancouver British Columbia", "Ketchikan Alaska", "Sitka Alaska", ...],
  "viking_data": {
    "itinerary_id": "2028_alaska-inside-passage_-_vancouver-british-columbia_to_seward",
    "cruise_name": "alaska_inside_passage",
    ...
  }
}
```

### Pricing Response

```json
{
  "success": true,
  "name": "Alaska & the Inside Passage",
  "year": "2028",
  "duration_days": 11,
  "starting_price": "$5,999",
  "sailings": [
    {
      "date": "May 4, 2028",
      "from_port": "Vancouver, British Columbia",
      "to_port": "Seward, Alaska",
      "cruise_fare": "$5,999",
      "air_fare": "$799",
      "promotion": "NEW Departure"
    },
    {
      "date": "May 14, 2028",
      "from_port": "Seward, Alaska",
      "to_port": "Vancouver, British Columbia",
      "cruise_fare": "$5,999",
      "air_fare": "$799",
      "promotion": "NEW Departure"
    },
    ...
  ],
  "promotions": ["NEW Departure", "Summer Sale"]
}
```

## Data Sources

The skill extracts data from:

1. **JSON-LD structured data** - Schema.org TouristTrip data embedded in the page
2. **Viking page data** - JavaScript objects (`window.viking_page_data`) containing cruise metadata
3. **Page content** - Visible text parsed for pricing and sailing information

## Notes

- The skill uses Playwright browser automation to bypass CloudFront protection
- Pages require proper browser headers to load successfully
- Pricing data is dynamically loaded and may require clicking on year tabs
- Some cruise routes may have different URL structures

## Known Cruise Routes

- **Alaska & the Inside Passage**: `alaska-inside-passage` in `caribbean-americas` region
  - Vancouver to Seward
  - Seward to Vancouver

More routes can be discovered by browsing vikingcruises.com directly.
