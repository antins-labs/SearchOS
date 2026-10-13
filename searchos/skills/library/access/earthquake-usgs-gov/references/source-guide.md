# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# USGS Earthquake FDSN API Access Skill

This skill provides structured access to the USGS Earthquake Hazards Program's FDSN (Federation of Digital Seismograph Networks) web service, delivering parsed earthquake data in a clean, structured format.

## Overview

The USGS FDSN API provides comprehensive earthquake data including:
- Real-time and historical earthquake information
- Magnitude, location, depth, and timing data
- Impact metrics (felt reports, PAGER alerts, tsunami warnings)
- Seismic network metadata

## Functions

### `query` - Search Earthquake Events

Query earthquake events with various filters. Returns a structured list of earthquakes with parsed data.

**Common Parameters:**
- `starttime`, `endtime`: ISO-8601 datetime strings (e.g., "2025-09-01T00:00:00")
- `minmagnitude`, `maxmagnitude`: Filter by magnitude range
- `minlatitude`, `maxlatitude`, `minlongitude`, `maxlongitude`: Bounding box filter
- `latitude`, `longitude`, `maxradiuskm`: Circular area filter
- `limit`: Maximum number of results
- `orderby`: Sort order ("time", "time-asc", "magnitude", "magnitude-asc")

**Example Request:**
```json
{
  "function": "query",
  "starttime": "2025-09-01T00:00:00",
  "endtime": "2025-09-30T23:59:59",
  "minmagnitude": 6.0,
  "orderby": "magnitude"
}
```

**Response Structure:**
```json
{
  "success": true,
  "count": 11,
  "total_available": 11,
  "events": [
    {
      "id": "us6000rdta",
      "magnitude": 6.0,
      "magnitude_type": "mb",
      "place": "31 km ESE of Kalianget, Indonesia",
      "time": "2025-09-15T12:34:56Z",
      "title": "M 6.0 - 31 km ESE of Kalianget, Indonesia",
      "location": {
        "longitude": 114.1844,
        "latitude": -7.2032,
        "depth_km": 19.498
      },
      "alert": "green",
      "tsunami": 0,
      "felt_reports": 124,
      "significance": 456
    }
  ]
}
```

### `count` - Count Matching Events

Returns the count of earthquakes matching the specified criteria without fetching full event data. Useful for checking data availability before large queries.

**Example Request:**
```json
{
  "function": "count",
  "starttime": "2025-01-01T00:00:00",
  "endtime": "2025-12-31T23:59:59",
  "minmagnitude": 5.0
}
```

**Response:**
```json
{
  "success": true,
  "count": 1523,
  "max_allowed": 20000
}
```

### `detail` - Get Event Details

Retrieve comprehensive information for a specific earthquake event by its USGS event ID.

**Example Request:**
```json
{
  "function": "detail",
  "eventid": "us6000rdta"
}
```

## Data Fields

Each earthquake event includes:

| Field | Description |
|-------|-------------|
| `id` | USGS event identifier |
| `magnitude` | Earthquake magnitude |
| `magnitude_type` | Magnitude scale (ml, ms, mb, mw, etc.) |
| `place` | Human-readable location description |
| `time` | ISO-8601 UTC timestamp |
| `location.longitude` | Longitude in degrees |
| `location.latitude` | Latitude in degrees |
| `location.depth_km` | Depth in kilometers |
| `significance` | Significance score (0-1000) |
| `alert` | PAGER alert level (green/yellow/orange/red) |
| `tsunami` | Tsunami flag (0 or 1) |
| `felt_reports` | Number of DYFI reports |
| `cdi` | Community Decimal Intensity |
| `mmi` | Modified Mercalli Intensity |
| `url` | USGS event page URL |

## Use Cases

1. **Recent Significant Earthquakes**: Query for magnitude 5+ earthquakes in the past week
2. **Regional Monitoring**: Use bounding box or circular filters for specific geographic areas
3. **Historical Analysis**: Query historical data for specific time periods
4. **Impact Assessment**: Filter by alert level or felt reports for significant events
5. **Event Verification**: Look up specific events by ID for detailed information

## Notes

- The API returns GeoJSON FeatureCollections which this skill parses into structured data
- Timestamps are converted from Unix milliseconds to ISO-8601 format
- Empty results return success with zero count (not an error)
- Maximum query results is 20,000 events; use filters and pagination for larger datasets
- The service has rate limits; implement retry logic for production use
