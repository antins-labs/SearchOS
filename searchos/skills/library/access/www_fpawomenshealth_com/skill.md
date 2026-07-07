# FPA Women's Health Clinic Location Scraper

This skill fetches clinic location information from FPA Women's Health website (www.fpawomenshealth.com), including addresses, phone numbers, office hours, services offered, and Google Maps coordinates.

## Available Functions

### list_locations
Get a list of all FPA Women's Health clinic locations.

**Example:**
```json
{
  "function": "list_locations"
}
```

**Returns:**
```json
{
  "total": 25,
  "locations": [
    {
      "id": 12,
      "name": "Bakersfield",
      "slug": "bakersfield",
      "url": "https://www.fpawomenshealth.com/locations/detail/12/bakersfield"
    },
    ...
  ]
}
```

### get_location
Get detailed information for a specific clinic location.

**Parameters:**
- `location_id` (required): Numeric ID of the location
- `slug` (required): URL slug of the location name

**Example:**
```json
{
  "function": "get_location",
  "location_id": 13,
  "slug": "fresno"
}
```

**Returns:**
```json
{
  "location_id": 13,
  "slug": "fresno",
  "name": "Fresno",
  "address": "165 N. Clark Street",
  "city_state_zip": "Fresno, CA 93701",
  "phone": "559-233-8657",
  "hours": {
    "Monday": "8:00 am to 5:00 pm",
    "Tuesday": "8:00 am to 5:00 pm",
    "Wednesday": "8:00 am to 5:00 pm",
    "Thursday": "8:00 am to 5:00 pm",
    "Friday": "8:00 am to 5:00 pm",
    "Saturday": "Closed",
    "Sunday": "Closed"
  },
  "services": [
    "Abortion - Medical (Pill)",
    "Abortion - Surgical",
    "Birth Control Pills",
    ...
  ],
  "latitude": 36.744558,
  "longitude": -119.786757,
  "map_url": "https://maps.google.com/maps?...",
  "yelp_url": "https://www.yelp.com/biz/...",
  "google_reviews_url": "https://www.google.com/maps?...",
  "description": "If you are in need of Women's Health..."
}
```

### search_locations
Search for locations by name (case-insensitive partial match).

**Parameters:**
- `query` (required): Search term to match against location names

**Example:**
```json
{
  "function": "search_locations",
  "query": "los"
}
```

**Returns:**
```json
{
  "query": "los",
  "total_matches": 1,
  "matches": [
    {
      "id": 6,
      "name": "Los Angeles (Downtown)",
      "slug": "los-angeles-downtown",
      "url": "https://www.fpawomenshealth.com/locations/detail/6/los-angeles-downtown"
    }
  ]
}
```

### get_multiple_locations
Get details for multiple clinic locations at once (up to 10).

**Parameters:**
- `locations` (required): Array of objects with `id` and `slug` keys

**Example:**
```json
{
  "function": "get_multiple_locations",
  "locations": [
    {"id": 13, "slug": "fresno"},
    {"id": 12, "slug": "bakersfield"}
  ]
}
```

## Data Source

Data is scraped from the public FPA Women's Health website. The location list is extracted from JSON-LD structured data embedded in the pages, and individual location details are parsed from the HTML content.

## Available Locations

FPA Women's Health operates 25 clinics across California:

- Bakersfield (ID: 12)
- Berkeley (ID: 23)
- Canoga Park (ID: 15)
- Chula Vista (ID: 19)
- Corona (ID: 20)
- Downey (ID: 2)
- East LA (ID: 3)
- Fresno (ID: 13)
- Glendale (ID: 16)
- Inglewood (ID: 4)
- Lancaster (ID: 14)
- Long Beach (ID: 5)
- Los Angeles (Downtown) (ID: 6)
- Mission Hills (ID: 17)
- Modesto (ID: 24)
- Oxnard (ID: 18)
- San Bernardino (ID: 21)
- Santa Ana (ID: 11)
- Santa Monica (ID: 8)
- Stockton (ID: 28)
- Temecula (ID: 22)
- Torrance (ID: 9)
- Tulare (ID: 27)
- Upland (ID: 7)
- West Covina (ID: 10)

## Notes

- The website uses static HTML rendering; no JavaScript execution is required
- Location IDs and slugs are required together to fetch location details
- Use `list_locations` or `search_locations` first to discover available locations and their IDs/slugs