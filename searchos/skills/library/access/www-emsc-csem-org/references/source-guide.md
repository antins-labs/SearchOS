# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# EMSC-CSEM Earthquake Information Access Skill

This skill retrieves detailed earthquake event data from the European Mediterranean Seismological Centre (EMSC-CSEM) website.

## Supported URLs

The skill works with both EMSC URL formats:
- `https://www.emsc-csem.org/Earthquake/earthquake.php?id={id}`
- `https://www.emsc-csem.org/Earthquake_information/earthquake.php?id={id}`

Note: The first URL format redirects to the second, but both are handled transparently.

## Functions

### get_earthquake

Retrieves comprehensive earthquake event data by ID.

**Parameters:**
- `earthquake_id` (required): The EMSC event ID (numeric string or integer)

**Returns:**
- `success`: Boolean indicating if the request succeeded
- `found`: Boolean indicating if the earthquake record exists
- `earthquake_id`: The requested event ID
- `magnitude`: Earthquake magnitude (e.g., "6.1")
- `region`: Geographic region name
- `datetime_utc`: Date and time in UTC (e.g., "2025-09-18 18:19:47.7 UTC")
- `latitude`: Latitude coordinate (float)
- `longitude`: Longitude coordinate (float)
- `location`: Raw location string (e.g., "-3.511 ; 135.521")
- `depth_km`: Depth in kilometers (float)
- `depth_raw`: Raw depth string (e.g., "15 km")
- `nearby_cities`: Array of nearby population centers with distance/direction
- `source_status`: Review status (e.g., "Source parameters reviewed by a seismologist")
- `data_providers`: Array of contributing seismological agencies
- `map_image_url`: URL to the event map thumbnail
- `url`: Final URL after any redirects

**Example Usage:**
```json
{
  "function": "get_earthquake",
  "earthquake_id": "1867478"
}
```

**Example Response:**
```json
{
  "success": true,
  "found": true,
  "earthquake_id": "1867478",
  "magnitude": "6.1",
  "region": "PAPUA, INDONESIA",
  "datetime_utc": "2025-09-18 18:19:47.7 UTC",
  "latitude": -3.511,
  "longitude": 135.521,
  "location": "-3.511 ; 135.521",
  "depth_km": 15.0,
  "depth_raw": "15 km",
  "nearby_cities": [
    {
      "distance_km": 556,
      "direction": "ESE",
      "city": "Sorong",
      "country": "Indonesia",
      "population": "125000"
    }
  ],
  "source_status": "Source parameters reviewed by a seismologist",
  "data_providers": [
    {"name": "Geoscience Australia", "location": "Canberra, Australia", "code": "AUST"},
    {"name": "British Geological Survey", "location": "Edinburgh, United Kingdom", "code": "BGS"}
  ],
  "url": "https://www.emsc-csem.org/Earthquake_information/earthquake.php?id=1867478"
}
```

## Error Handling

The skill returns structured error responses:

- **Missing earthquake_id**: Returns error with message indicating the required parameter
- **Invalid earthquake_id**: Returns error if the ID is not numeric
- **Non-existent ID**: Returns `found: false` with an error message (the site returns empty fields for invalid IDs)
- **Network errors**: Returns error with details about the failure

## Data Notes

- The EMSC site returns HTTP 200 with empty table fields for non-existent earthquake IDs
- The skill detects this by checking if the magnitude field is empty
- Magnitude is the primary indicator that an earthquake record exists
- The site may list multiple data providers who contributed parameters for the event
- Some events may have DOI links to additional scientific data
