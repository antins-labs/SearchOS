# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Egyptian Monuments Access Skill

Access structured data about ancient Egyptian monuments from the official Egyptian Ministry of Tourism and Antiquities website (egymonuments.gov.eg).

## Overview

This skill retrieves detailed information about Egyptian monuments including:
- Pyramids (Giza, Saqqara, Dahshur, etc.)
- Temples (Karnak, Luxor, Abu Simbel, etc.)
- Tombs (Valley of the Kings, etc.)
- Archaeological sites across Egypt

## Functions

### get_monument

Fetch a single monument by its URL slug or full URL.

**Parameters:**
- `slug` (string): The monument's URL slug, e.g., `the-step-pyramid-complex-of-djoser`
- `url` (string, optional): Full URL as alternative to slug
- `lang` (string, default: "en"): Language code ("en" for English, "ar" for Arabic)

**Example:**
```json
{
  "function": "get_monument",
  "slug": "the-step-pyramid-complex-of-djoser"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "url": "https://egymonuments.gov.eg/en/monuments/the-step-pyramid-complex-of-djoser",
    "slug": "the-step-pyramid-complex-of-djoser",
    "title": "The Step Pyramid Complex of Djoser",
    "location": "Saqqara",
    "description": "Djoser's Step Pyramid in Saqqara is one of Egypt's most iconic monuments...",
    "full_description": "Complete multi-paragraph description...",
    "main_image": {
      "src": "https://egymonuments.gov.eg/media/...",
      "alt": "The Step Pyramid Complex of Djoser"
    },
    "meta_description": "...",
    "keywords": ["Djoser's Step Pyramid", "Saqqara", ...]
  }
}
```

### get_multiple_monuments

Fetch multiple monuments in a single request.

**Parameters:**
- `slugs` (array of strings): List of monument slugs
- `urls` (array of strings, optional): List of full URLs
- `lang` (string, default: "en"): Language code

**Example:**
```json
{
  "function": "get_multiple_monuments",
  "slugs": [
    "the-step-pyramid-complex-of-djoser",
    "the-pyramid-of-meidum",
    "pyramid-complex-of-teti"
  ]
}
```

### search_monuments

Search for monuments by keyword.

**Parameters:**
- `query` (string): Search query
- `lang` (string, default: "en"): Language code

**Example:**
```json
{
  "function": "search_monuments",
  "query": "pyramid"
}
```

**Note:** Search functionality is limited as the site uses dynamic content loading. Results may vary.

## Data Fields

Each monument record contains:

| Field | Description |
|-------|-------------|
| `url` | Full URL of the monument page |
| `slug` | URL identifier for the monument |
| `title` | Official name of the monument |
| `location` | Site/location name (e.g., "Saqqara", "Giza") |
| `description` | Short description/introduction |
| `full_description` | Complete detailed description |
| `main_image` | Primary image with `src` and `alt` |
| `meta_description` | SEO meta description |
| `keywords` | List of keywords/tags |
| `opening_hours` | Visiting hours if available |
| `tickets` | Ticket information if available |

## Example Monument Slugs

Some well-known monuments and their slugs:

- `the-step-pyramid-complex-of-djoser` - Djoser's Step Pyramid at Saqqara
- `the-pyramid-of-meidum` - Meidum Pyramid
- `pyramid-complex-of-teti` - Teti Pyramid Complex at Saqqara

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Monument not found: https://...",
  "status_code": 404,
  "data": null
}
```

## Notes

- The site is operated by the Egyptian Ministry of Tourism and Antiquities
- Content is available in English (`en`) and Arabic (`ar`)
- Monument pages include historical information, descriptions, and images
- The site uses Umbraco CMS with server-side rendering
- No API key required for basic page access
