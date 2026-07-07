# National Park Visitation Data Access Skill

This skill provides access to National Park Service visitation statistics from [data.hereandthere.club](https://data.hereandthere.club), a comprehensive database of NPS visitor data spanning from 1979 to 2025.

## Data Available

The skill extracts the following information for each park:

### Core Statistics
- **Recreation Visits** - Number of recreational visitors
- **Total Visits** - Total visitors including non-recreational
- **Overnight Stays** - Visitors staying overnight in the park
- **Total Campers** - Campers (tent, RV, backcountry)
- **Average Visit Duration** - Hours per visit
- **Peak Month** - Busiest month of the year
- **Recreation Hours** - Total hours spent in recreation

### Camping Breakdown
- Tent Campers
- RV Campers
- Backcountry Campers

### Overnight Stays Breakdown
- Tent Camping
- RV Camping
- Backcountry
- Concessioner Lodging
- Miscellaneous Overnight

### Park Information
- State/Location
- Region
- Establishment Date
- Size (acres)

## Functions

### `get_park_data`

Get detailed visitation data for a specific park.

**Parameters:**
- `park` (required): Park slug identifier
- `year` (optional): Year of data (1979-2025)

**Examples:**

```python
# Get latest data for Zion National Park
result = await execute({
    "function": "get_park_data",
    "park": "zion"
})

# Get 2023 data for Yellowstone
result = await execute({
    "function": "get_park_data", 
    "park": "yellowstone",
    "year": 2023
})

# Get Pearl Harbor National Memorial data
result = await execute({
    "function": "get_park_data",
    "park": "pearl-harbor-nmem",
    "year": 2023
})

# Get Muir Woods National Monument data
result = await execute({
    "function": "get_park_data",
    "park": "muir-woods"
})
```

**Sample Response:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "year": 2023,
    "park_name": "Zion National Park",
    "designation": "National Parks",
    "slug": "zion",
    "recreation_visits": 4620000,
    "recreation_visits_str": "4.62M",
    "overnight_stays": 320400,
    "overnight_stays_str": "320.4K",
    "recreation_hours": 29470000,
    "recreation_hours_str": "29.47M",
    "statistics": {
      "recreation_visits": {"value": 4620000, "value_str": "4.62M"},
      "total_visits": {"value": 4650000, "value_str": "4.65M"},
      "overnight_stays": {"value": 320400, "value_str": "320.4K"}
    },
    "park_info": {
      "state": "Utah",
      "region": "Intermountain",
      "established": "November 19, 1919",
      "size": "147,237 acres"
    },
    "peak_month": "June"
  }
}
```

### `list_parks`

List available parks, optionally filtered by designation.

**Parameters:**
- `designation` (optional): Filter by designation type

**Examples:**

```python
# List all parks
result = await execute({"function": "list_parks"})

# List only national parks
result = await execute({
    "function": "list_parks",
    "designation": "national-parks"
})

# List national monuments
result = await execute({
    "function": "list_parks",
    "designation": "national-monuments"
})
```

**Sample Response:**
```json
{
  "success": true,
  "data": {
    "count": 64,
    "designation": "national-parks",
    "parks": [
      {"name": "Acadia National Park", "slug": "acadia", "url": "..."},
      {"name": "Arches National Park", "slug": "arches", "url": "..."},
      {"name": "Badlands National Park", "slug": "badlands", "url": "..."}
    ]
  }
}
```

### `get_summary`

Get summary statistics about the visitation dataset.

**Parameters:** None

**Example:**
```python
result = await execute({"function": "get_summary"})
```

## Park Slug Format

Park slugs are lowercase, hyphen-separated identifiers:

| Park Type | Examples |
|-----------|----------|
| National Parks | `zion`, `yellowstone`, `grand-canyon`, `yosemite` |
| National Monuments | `muir-woods`, `devils-tower`, `statue-of-liberty` |
| National Memorials | `pearl-harbor-nmem`, `lincoln-memorial` |
| National Recreation Areas | `lake-mead`, `golden-gate` |

Common suffixes in slugs:
- `-np` - National Park
- `-nm` - National Monument
- `-nmem` - National Memorial
- `-nra` - National Recreation Area
- `-nhs` - National Historic Site

## Data Coverage

- **Time Range**: 1979 - 2025
- **Park Types**: 63 National Parks plus National Monuments, Memorials, Historic Sites, Recreation Areas, and other NPS units
- **Data Source**: National Park Service Public Use Statistics

## Rate Limits

The skill implements conservative caching with a 1-hour TTL. Avoid making more than 30 requests per minute.

## Error Handling

All functions return structured responses with `success`, `error`, and `data` fields:

```json
{
  "success": false,
  "error": "HTTP 404: Failed to fetch...",
  "data": null
}
```

Common errors:
- Invalid park slug: Returns HTTP 404
- Invalid year: Falls back to most recent year or returns 404 if park not found
- Missing required parameter: Returns error message

## Notes

- The site is a Next.js application that renders data server-side
- Data is extracted from HTML content using structured parsing
- Historical data varies in completeness for earlier years
- Some parks may have limited data depending on when they were established