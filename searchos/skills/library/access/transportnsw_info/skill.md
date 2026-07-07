# Transport NSW Route Details Skill

Access Transport NSW route information including timetables, stops, and route details.

## Overview

This skill provides access to Transport NSW's route information through their GraphQL API. It retrieves comprehensive route data including:

- **Route details**: Name, number, direction, color, transport network
- **Stop lists**: Complete list of stops with IDs and names
- **GeoJSON data**: Route line geometry and stop locations
- **Schedule information**: Service dates and availability
- **Transport modes**: Commuter railway, metro, bus, ferry, light rail

## Functions

### get_route

Get detailed information about a specific route.

**Parameters:**
- `route_number` (string, required): Route number in short or full format (e.g., "T6" or "020T6")
- `date` (string, optional): Date in YYYY-MM-DD format (defaults to today)
- `include_geojson` (boolean, optional): Include GeoJSON data (default: true)

**Example:**
```python
result = await execute({
    "function": "get_route",
    "route_number": "T6"
})
```

**Returns:**
```json
{
  "success": true,
  "route": {
    "id": "020T6",
    "number": "T6",
    "name": "Lidcombe & Bankstown Line",
    "direction": "Bankstown to Lidcombe",
    "color": "#7C3E21",
    "transport_name": "Sydney Trains Network",
    "stops": [
      {"stop_id": "...", "name": "Bankstown Station"},
      {"stop_id": "...", "name": "Yagoona Station"},
      ...
    ],
    "geojson_line": {...},
    "geojson_stops": {...}
  }
}
```

### search_routes

Search for routes by name, number, or keyword.

**Parameters:**
- `query` (string, required): Search query
- `date` (string, optional): Date in YYYY-MM-DD format
- `limit` (integer, optional): Maximum results (default: 10)

**Example:**
```python
result = await execute({
    "function": "search_routes",
    "query": "Airport"
})
```

### get_alerts

Get page-specific alerts for a route page.

**Parameters:**
- `path` (string, required): Page path (e.g., "/routes/details/sydney-trains-network/t6/020t6")

**Example:**
```python
result = await execute({
    "function": "get_alerts",
    "path": "/routes/details/sydney-trains-network/t6/020t6"
})
```

## Supported Routes

Common Sydney Trains routes include:
- **T1**: North Shore & Western Line
- **T2**: Inner West & Leppington Line
- **T3**: Bankstown Line
- **T4**: Eastern Suburbs & Illawarra Line
- **T5**: Cumberland Line
- **T6**: Lidcombe & Bankstown Line
- **T7**: Olympic Park Line
- **T8**: Airport & South Line
- **T9**: Northern Line

## Data Retrieved

Each route provides:
- **Route metadata**: ID, number, name, direction, color
- **Stop information**: Complete stop list with IDs and names
- **Location data**: Parent station information
- **Geometry**: GeoJSON line (route path) and points (stops)
- **Schedule info**: Service dates and look-ahead period
- **Transport info**: Mode, network, Opal tariff

## Example Usage

### Basic Route Lookup
```python
result = await execute({
    "function": "get_route",
    "route_number": "T6"
})

if result["success"]:
    route = result["route"]
    print(f"{route['number']}: {route['name']}")
    print(f"Direction: {route['direction']}")
    print(f"Stops: {len(route['stops'])}")
```

### Route with Date
```python
result = await execute({
    "function": "get_route",
    "route_number": "T8",
    "date": "2026-06-22"
})
```

### Search Routes
```python
result = await execute({
    "function": "search_routes",
    "query": "Olympic"
})

if result["success"]:
    for route in result["routes"]:
        print(f"{route['number']}: {route['name']}")
```

## Technical Details

- **API**: GraphQL endpoint at `https://transportnsw.info/api/graphql`
- **Authentication**: None required for public route data
- **Rate limits**: Unknown (use responsibly)
- **Response format**: JSON

## Error Handling

All functions return a consistent structure:
```json
{
  "success": true/false,
  "error": "Error message if failed",
  "details": "Additional error details if available"
}
```

Always check `result["success"]` before accessing the data.

## Notes

- Route numbers can be specified in short format (e.g., "T6") - the skill automatically converts to the full format
- GeoJSON data can be large; set `include_geojson: false` if you don't need it
- The API returns upcoming service information for the specified date
- Different routes may have different look-ahead periods (typically 15 days)