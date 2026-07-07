# Natural England Defra ArcGIS Open Data Access Skill

Access geospatial datasets from Natural England and Defra's ArcGIS Open Data portal.

## Overview

This skill provides direct API access to the ArcGIS REST Service hosting Natural England's geospatial datasets. Currently implemented for the **Areas of Outstanding Natural Beauty (AONB) England** dataset.

## Dataset: Areas of Outstanding Natural Beauty (England)

- **Source**: Natural England / Defra
- **Total Features**: 34 AONBs
- **Geometry Type**: Polygon
- **Coordinate System**: British National Grid (EPSG:27700)
- **Update Frequency**: Periodic (last edit tracked in metadata)

### Available Attributes

| Field | Type | Description |
|-------|------|-------------|
| OBJECTID | integer | Unique identifier |
| CODE | string | 2-digit AONB code |
| NAME | string | Official AONB name |
| DESIG_DATE | string | Designation date (Mon-YY format) |
| HOTLINK | string | URL to official AONB website |
| STAT_AREA | float | Statistical area (km²) |
| Shape__Area | float | Geometry area (map units) |
| Shape__Length | float | Geometry perimeter (map units) |
| GlobalID | string | Global unique identifier (UUID) |

## Functions

### `list_aonbs`

List all AONBs in England with optional pagination.

**Parameters:**
- `include_geometry` (boolean, optional): Include polygon geometries. Default: `false`
- `limit` (integer, optional): Maximum records to return
- `offset` (integer, optional): Pagination offset. Default: `0`

**Example:**
```python
result = await execute({
    "function": "list_aonbs",
    "include_geometry": false,
    "limit": 10
})
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_count": 34,
    "returned_count": 10,
    "offset": 0,
    "limit": 10,
    "aonbs": [
      {
        "object_id": 1,
        "code": "11",
        "name": "East Devon",
        "designation_date": "Sep-63",
        "website_url": "https://www.eastdevon-nl.org.uk/",
        "area_sqkm": 269.13,
        "global_id": "3d6d2039-f86a-467b-a66a-9e988aea8bf2"
      }
    ]
  }
}
```

### `get_aonb`

Get a specific AONB by name or code.

**Parameters:**
- `name` (string, optional): Name of the AONB (case-insensitive)
- `code` (string, optional): 2-digit code of the AONB
- `include_geometry` (boolean, optional): Include polygon geometry. Default: `true`

**Example:**
```python
result = await execute({
    "function": "get_aonb",
    "name": "Cotswolds"
})
```

**Response:**
```json
{
  "success": true,
  "data": {
    "object_id": 4,
    "code": "7",
    "name": "Cotswolds",
    "designation_date": "Sep-66",
    "website_url": "https://www.cotswoldsaonb.org.uk/",
    "area_sqkm": 2041.09,
    "shape_area": 2042416258.8575,
    "shape_length": 743388.511757622,
    "global_id": "...",
    "geometry_type": "esriGeometryPolygon",
    "spatial_reference": {"wkid": 27700},
    "geometry": {"rings": [...]}
  }
}
```

### `search`

Search AONBs by criteria.

**Parameters:**
- `query` (string, optional): Name substring search (case-insensitive)
- `min_area` (float, optional): Minimum area in km²
- `max_area` (float, optional): Maximum area in km²
- `include_geometry` (boolean, optional): Include polygons. Default: `false`

**Example - Find large AONBs:**
```python
result = await execute({
    "function": "search",
    "min_area": 1000
})
```

**Example - Search by name:**
```python
result = await execute({
    "function": "search",
    "query": "Devon"
})
```

### `get_metadata`

Get comprehensive dataset metadata.

**Example:**
```python
result = await execute({"function": "get_metadata"})
```

**Response includes:**
- Service information
- Layer details
- Field definitions
- Feature count
- Extent and spatial reference
- Capabilities

## API Details

### ArcGIS REST Endpoint

```
Base URL: https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Areas_of_Outstanding_Natural_Beauty_England/FeatureServer
Layer: /0 (AONB polygons)
```

### Query Parameters

The skill constructs ArcGIS REST API queries with:
- `f=json`: JSON response format
- `where`: SQL where clause for filtering
- `outFields`: Fields to return (* for all)
- `returnGeometry`: Include polygon geometries
- `orderByFields`: Sort results
- `resultOffset` / `resultRecordCount`: Pagination

## Usage Notes

1. **Geometry Size**: Polygon geometries can be large. Only request geometry when needed.
2. **Case Insensitivity**: Name searches are case-insensitive.
3. **Area Units**: `STAT_AREA` is in square kilometers; `Shape__Area` is in map units.
4. **Spatial Reference**: All geometries are in British National Grid (EPSG:27700).
5. **Max Records**: Service supports up to 1000 records per request.

## Dataset Highlights

- **Largest AONB**: Cotswolds (2,041 km²)
- **Smallest AONB**: Cannock Chase (68.65 km²)
- **Total AONB Area**: ~21,000 km² combined
- All AONBs include official website links

## Error Handling

All functions return structured error responses:
```json
{
  "success": false,
  "error": "Error description"
}
```

Common errors:
- Missing required parameters
- No matching AONB found
- Network/API errors