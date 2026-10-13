# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Metropolitan Museum of Art Collection Access Skill

Access artwork details from The Metropolitan Museum of Art's collection through their public API.

## Overview

This skill retrieves structured artwork information from The Met's collection database, including:
- Artwork details (title, artist, date, medium, dimensions)
- Image URLs (primary and additional images)
- Provenance and credit information
- Gallery location and exhibition status
- Related metadata (culture, period, classification)

## Functions

### get_object

Retrieve detailed information about a specific artwork by its object ID.

**Parameters:**
- `object_id` (required): The Met's object ID (integer)

**Example:**
```json
{
  "function": "get_object",
  "object_id": 922250
}
```

**Returns:**
```json
{
  "success": true,
  "object": {
    "object_id": 922250,
    "title": "Go By Shank's Pony",
    "artist": {
      "name": "Jan Le Witt",
      "bio": "British, born Poland, 1907–1991"
    },
    "date": "ca. 1943",
    "medium": "Lithograph",
    "dimensions": "Sheet: 29 15/16 × 20 1/16 in. (76 × 51 cm)",
    "classification": "Posters",
    "department": "Drawings and Prints",
    "images": {...},
    ...
  }
}
```

### search

Search the collection with various filters.

**Parameters:**
- `query` (optional): Search keywords (default: "*")
- `department_id` (optional): Filter by department ID
- `has_images` (optional): Boolean - only return objects with images
- `is_highlight` (optional): Boolean - only return highlighted objects
- `is_on_view` (optional): Boolean - only return objects currently on display
- `artist_or_culture` (optional): Boolean - search in artist or culture fields
- `title` (optional): Boolean - search only in titles
- `geo_location` (optional): Filter by geographic location
- `medium` (optional): Filter by medium/material
- `date_begin` (optional): Start year for date range
- `date_end` (optional): End year for date range

**Examples:**

Search for Van Gogh works:
```json
{
  "function": "search",
  "query": "van gogh",
  "has_images": true
}
```

Search for highlights currently on view:
```json
{
  "function": "search",
  "query": "*",
  "is_highlight": true,
  "is_on_view": true
}
```

Search by date range:
```json
{
  "function": "search",
  "query": "war",
  "date_begin": 1940,
  "date_end": 1945,
  "has_images": true
}
```

**Returns:**
```json
{
  "success": true,
  "total": 427,
  "object_ids": [459123, 436533, 436535, ...]
}
```

### departments

Get a list of all museum departments with their IDs.

**Parameters:** None

**Example:**
```json
{
  "function": "departments"
}
```

**Returns:**
```json
{
  "success": true,
  "departments": [
    {"id": 1, "name": "American Decorative Arts"},
    {"id": 3, "name": "Ancient West Asian Art"},
    {"id": 4, "name": "Arms and Armor"},
    ...
  ]
}
```

## Common Object IDs for Testing

- `922250` - "Go By Shank's Pony" by Jan Le Witt
- `922254` - "Food needs transport - don't waste it" by Jan Le Witt
- `922258` - "Milk - The Backbone of Young Britain" by James Fitton
- `436533` - "Wheat Field with Cypresses" by Vincent van Gogh
- `437984` - "Self-Portrait" by Vincent van Gogh

## Notes

- The Met's public API does not require authentication
- Rate limiting is not explicitly documented, but reasonable request intervals are recommended
- Object IDs can be found in The Met's collection URLs (e.g., metmuseum.org/art/collection/search/922250)
- Images marked as `isPublicDomain: true` are available for unrestricted use
- Use the `search` function to discover object IDs, then `get_object` for full details
