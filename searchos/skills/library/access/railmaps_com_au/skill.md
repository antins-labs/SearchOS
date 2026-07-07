# Rail Maps Australia - Route Details Skill

This skill fetches timetable route information from [railmaps.com.au](https://railmaps.com.au), an Australian rail timetable portal that provides comprehensive information about train, tram, ferry, and bus routes across Australia.

## Features

- **Route Details**: Fetch metadata, station lists, and provider information for any route
- **Schema.org Data**: Extract structured JSON-LD data including complete station itineraries
- **Multiple Operators**: Works with various operators including:
  - Sydney Trains (T-Number routes, e.g., T7 Olympic Park line)
  - Journey Beyond Rail (Indian Pacific, The Ghan, Great Southern)
  - NSW TrainLink (XPT services)
  - Queensland Rail (Spirit of Queensland, The Gulflander)
  - And many more

## Known Route IDs

The following TableSelect IDs are known to work:

| ID | Route Name |
|----|------------|
| 1 | The Indian Pacific (Sydney-Perth) |
| 2 | The Ghan (Adelaide-Darwin) |
| 22 | Southern Spirit |
| 24 | The Overland (Melbourne-Adelaide) |
| 25 | Spirit of Tasmania |
| 26 | Great Southern |
| 44-47 | XPT Services (NSW TrainLink) |
| 48 | Spirit of Queensland |
| 49 | Cairns Kuranda Railway |
| 52 | The Gulflander |
| 64 | The Savannahlander |
| 73 | Sydney Ferries |
| 212 | T7 Olympic Park line (Sydney Trains) |

## Usage Examples

### Get Route Details

Fetch complete route information including stations and metadata:

```python
result = await execute({
    'function': 'get_route_details',
    'table_select': 212  # T7 Olympic Park line
})
```

Returns:
```json
{
  "success": true,
  "table_select": 212,
  "route": {
    "name": "T7 Olympic Park line",
    "provider": "Sydney Trains",
    "station_count": 4
  },
  "stations": ["Sydney Central", "Strathfield", "Lidcombe", "Olympic Park"],
  "json_ld": { ... },
  "timetable": {
    "rows": 0,
    "has_data": false
  }
}
```

### Search Routes

Get a list of available routes:

```python
result = await execute({
    'function': 'search_routes'
})
```

Filter by name:

```python
result = await execute({
    'function': 'search_routes',
    'query': 'Pacific'
})
```

## Data Sources

This skill extracts data from:

1. **HTML meta tags**: Title, description, keywords, Open Graph data
2. **JSON-LD structured data**: Complete Schema.org TrainTrip data with station itinerary
3. **JavaScript variables**: RouteSelect, Source, Anchor_Station, and other internal IDs
4. **AJAX endpoint**: Timetable data (when available via routedetails_AJAX.php)

## Notes

- The site uses Cloudflare protection; some routes may be temporarily blocked
- Timetable AJAX data may return 0 rows due to date restrictions or service availability
- Route metadata and station lists are typically available even when timetable data is not
- The skill uses direct HTTP requests for fast retrieval without browser overhead