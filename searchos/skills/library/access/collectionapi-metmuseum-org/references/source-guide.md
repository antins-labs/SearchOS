# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Metropolitan Museum of Art Collection API

Access the Met's public collection API to retrieve artwork records, search the
collection, and explore museum departments.

## Features

- **get_object**: Retrieve detailed metadata for a single artwork by object ID
- **search**: Search the collection with powerful filters (images, department,
  medium, date range, etc.)
- **departments**: List all museum departments with IDs for filtering
- **get_objects_batch**: Retrieve multiple artworks efficiently in one call

## Usage Examples

### Get a Single Object

```json
{
  "function": "get_object",
  "object_id": 922242
}
```

Returns complete object record including title, artist, date, medium,
dimensions, images, department, credit line, and more.

### Search the Collection

Basic search:
```json
{
  "function": "search",
  "query": "van gogh"
}
```

Search with filters:
```json
{
  "function": "search",
  "query": "painting",
  "has_images": true,
  "department": "11",
  "date_begin": 1800,
  "date_end": 1900
}
```

### Get Departments

```json
{
  "function": "departments"
}
```

Returns department IDs and names for use in search filters.

### Batch Retrieve Objects

```json
{
  "function": "get_objects_batch",
  "object_ids": [922242, 922243, 436533]
}
```

## Response Structure

### Object Record

```json
{
  "success": true,
  "object": {
    "id": 922242,
    "title": "Food is a Munition of War - Don't Waste It",
    "artist": "J. Weiner Ltd.",
    "artist_bio": "British, active 1912–after 1945",
    "date": "ca. 1940–45",
    "medium": "Lithograph",
    "department": "Drawings and Prints",
    "classification": "Posters",
    "is_public_domain": false,
    "primary_image": "...",
    "object_url": "https://www.metmuseum.org/art/collection/search/922242"
  },
  "raw": { ... }
}
```

### Search Results

```json
{
  "success": true,
  "total": 435,
  "object_ids": [459123, 436533, 436535, ...],
  "query": "van gogh",
  "filters": { ... }
}
```

## Notes

- The Met API is public and requires no authentication
- Object IDs can be obtained via search or from Met website URLs
- Empty strings in responses indicate unavailable data
- The `raw` field in get_object contains the complete API response
- Use `has_images: true` to filter for objects with viewable images
- Department IDs are numeric strings (e.g., "11" for European Paintings)
