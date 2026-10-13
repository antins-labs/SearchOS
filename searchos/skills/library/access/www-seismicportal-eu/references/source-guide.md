# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Seismic Portal FDSNWS Event API

This skill retrieves earthquake event data from the European-Mediterranean
Seismological Centre (EMSC) Seismic Portal via the FDSNWS Event web service.

## Capabilities

### search_events
Flexible earthquake search with multiple filter options:

- **Temporal**: `starttime`, `endtime` (ISO 8601 format)
- **Magnitude**: `minmagnitude`, `maxmagnitude`
- **Depth**: `mindepth`, `maxdepth` (kilometers)
- **Geographic bounding box**: `minlatitude`, `maxlatitude`, `minlongitude`, `maxlongitude`
- **Circular search**: `latitude`, `longitude`, `maxradius`, `minradius`
- **Result control**: `limit`, `offset`, `orderby`

Example: Find magnitude 6+ earthquakes in September 2025
```json
{
  "function": "search_events",
  "starttime": "2025-09-01T00:00:00",
  "endtime": "2025-09-30T23:59:59",
  "minmagnitude": 6.0
}
```

Example: Find earthquakes near Japan
```json
{
  "function": "search_events",
  "starttime": "2025-01-01T00:00:00",
  "endtime": "2025-12-31T23:59:59",
  "minlatitude": 30.0,
  "maxlatitude": 46.0,
  "minlongitude": 129.0,
  "maxlongitude": 146.0,
  "minmagnitude": 5.0,
  "limit": 20
}
```

### get_event
Retrieve a specific earthquake by its unique identifier.

Example:
```json
{
  "function": "get_event",
  "eventid": "20250930_0000258"
}
```

### list_recent
Convenience function to list recent significant earthquakes.

Parameters:
- `days_back`: Number of days to look back (default: 30)
- `minmagnitude`: Minimum magnitude threshold (default: 5.0)
- `limit`: Maximum number of results (default: 50)

Example:
```json
{
  "function": "list_recent",
  "days_back": 7,
  "minmagnitude": 5.5,
  "limit": 20
}
```

## Response Structure

Each event record contains:

| Field | Description |
|-------|-------------|
| `event_id` | Unique event identifier |
| `source_id` | Source catalog event ID |
| `source_catalog` | Catalog name (e.g., EMSC-RTS) |
| `time` | Event origin time (ISO 8601) |
| `lastupdate` | Last update time |
| `latitude` | Epicenter latitude |
| `longitude` | Epicenter longitude |
| `depth_km` | Focal depth in kilometers |
| `region` | Geographic region name |
| `magnitude` | Magnitude value |
| `magnitude_type` | Magnitude type (mw, mb, ml, etc.) |
| `event_type` | Event type code (ke = earthquake) |
| `authority` | Reporting authority |

## Notes

- The API returns GeoJSON FeatureCollection for searches, and a single Feature for event ID lookups
- HTTP 204 indicates no matching events (empty result set)
- Time format: ISO 8601 (e.g., `2025-09-01T00:00:00`)
- Magnitude types: mw (moment), mb (body), ml (local), ms (surface)
