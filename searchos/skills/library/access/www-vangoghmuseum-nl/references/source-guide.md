# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Van Gogh Museum Collection Access Skill

This skill fetches detailed information about artworks from the Van Gogh Museum's online collection at [www.vangoghmuseum.nl](https://www.vangoghmuseum.nl).

## Features

- Retrieves comprehensive artwork details including:
  - Title and description
  - Artist information (Vincent van Gogh, 1853-1890)
  - Creation location, period, and year
  - Medium (e.g., oil on canvas)
  - Dimensions (height × width in cm)
  - Current display status (on view or not)
  - Credits and attribution
  - High-resolution image URLs via IIIF

- Bypasses the Cookiebot consent wall automatically

## Functions

### get_artwork

Fetches detailed information about a specific artwork.

**Parameters:**
- `object_id` (required): The artwork's object number, e.g., `s0160V1962`

**Example:**
```json
{
  "function": "get_artwork",
  "object_id": "s0160V1962"
}
```

**Returns:**
```json
{
  "success": true,
  "object_id": "s0160V1962",
  "url": "https://www.vangoghmuseum.nl/en/collection/s0160V1962",
  "title": "Self-Portrait as a Painter",
  "description": "This is one of the earliest self-portraits painted by Van Gogh...",
  "artist": "Vincent van Gogh",
  "artist_birth_year": 1853,
  "artist_death_year": 1890,
  "creation_location": "Paris",
  "creation_period": "September-November",
  "creation_year": 1886,
  "medium": "oil on canvas",
  "dimensions": "46.5 cm x 38.5 cm",
  "height_cm": 46.5,
  "width_cm": 38.5,
  "on_view": true,
  "credits": "Van Gogh Museum, Amsterdam (Vincent van Gogh Foundation)",
  "image_url": "https://iiif.micr.io/ugeeH/full/1280,/0/default.jpg",
  "iiif_base_url": "https://iiif.micr.io/ugeeH"
}
```

### get_iiif_url

Generates a IIIF image URL for a specific width.

**Parameters:**
- `iiif_base_url` (required): The IIIF base URL from `get_artwork` results
- `width` (optional): Desired width in pixels (default: 1280)

**Example:**
```json
{
  "function": "get_iiif_url",
  "iiif_base_url": "https://iiif.micr.io/ugeeH",
  "width": 2560
}
```

**Returns:**
```json
{
  "success": true,
  "iiif_url": "https://iiif.micr.io/ugeeH/full/2560,/0/default.jpg",
  "width": 2560
}
```

## Object IDs

Object IDs follow patterns like:
- `s0160V1962` - Standard format
- `s0097V1962v` - With version suffix (v)
- `s0022v1962` - Lowercase variant

You can find object IDs in the collection page URLs on the Van Gogh Museum website.

## Known Artworks

Some notable object IDs for testing:
- `s0160V1962` - Self-Portrait as a Painter (1886)
- `s0097V1962v` - Self-Portrait (1887)
- `s0022v1962` - Self-Portrait as a Painter (1887-1888)

## Error Handling

The skill returns structured error responses:
- HTTP 404: Artwork not found
- Timeout: Request timed out
- Missing parameters: Required field not provided

## Technical Notes

- Uses Cookiebot consent cookie to bypass the cookie consent wall
- Parses HTML meta tags and structured content for artwork data
- Supports IIIF image API for requesting images at different resolutions
- All requests include proper User-Agent headers for compatibility
