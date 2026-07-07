# ISHOF (International Swimming Hall of Fame) Access Skill

Access honoree biography records from the International Swimming Hall of Fame website via its WordPress REST API.

## Overview

This skill provides programmatic access to ISHOF's database of swimming hall of fame inductees. The site hosts detailed biographical information about swimmers, divers, water polo players, synchronized swimmers, coaches, and contributors who have been honored by the International Swimming Hall of Fame.

## Available Functions

### list_honorees

Retrieve a paginated list of all honorees.

**Parameters:**
- `page` (integer, optional): Page number, default 1
- `per_page` (integer, optional): Results per page, default 20, max 100
- `include_content` (boolean, optional): Include full biography text, default false
- `include_ids` (string, optional): Comma-separated list of specific IDs to retrieve

**Example:**
```json
{"function": "list_honorees", "per_page": 10}
```

### get_honoree

Retrieve a single honoree by ID or slug.

**Parameters:**
- `id` (integer, optional): WordPress post ID
- `slug` (string, optional): URL slug like "michael-phelps"
- `include_content` (boolean, optional): Include full biography, default true

**Example:**
```json
{"function": "get_honoree", "slug": "michael-phelps"}
```

### search_honorees

Search honorees by keyword.

**Parameters:**
- `query` (string, required): Search term
- `per_page` (integer, optional): Max results, default 20
- `include_content` (boolean, optional): Include full biography, default false

**Example:**
```json
{"function": "search_honorees", "query": "olympic gold"}
```

### list_categories

Get all available honoree categories.

**Example:**
```json
{"function": "list_categories"}
```

**Returns:**
- ISHOF Honoree (regular inductees)
- Masters Honoree (masters swimming)
- Relay Team
- Team
- ISH (International Swimming Hall special category)

### honorees_by_category

Filter honorees by category.

**Parameters:**
- `category` (string, required): Category ID or slug (e.g., "ishof-honoree", "masters-honoree", "team")
- `page` (integer, optional): Page number
- `per_page` (integer, optional): Results per page
- `include_content` (boolean, optional): Include full biography

**Example:**
```json
{"function": "honorees_by_category", "category": "masters-honoree", "per_page": 15}
```

## Data Structure

Each honoree record includes:

| Field | Description |
|-------|-------------|
| `id` | WordPress post ID |
| `slug` | URL-friendly identifier |
| `title` | Full name |
| `link` | Web page URL |
| `date` | Publication date |
| `modified` | Last modified date |
| `categories` | Category IDs |
| `featured_image` | Photo with URL, alt text, dimensions |
| `content_raw` | Full HTML biography (if include_content=true) |
| `content_text` | Plain text biography (if include_content=true) |
| `meta.description` | SEO description |

## Category Reference

| Slug | ID | Description |
|------|------|-------------|
| ishof-honoree | 35 | Primary ISHOF inductees |
| ishof-honorees | 52 | Alternative category |
| masters-honoree | 36 | Masters swimming honorees |
| relay-team | 49 | Relay team inductees |
| team | 50 | Team inductees |
| ish | 53 | International Swimming Hall special |

## Examples

### Get Michael Phelps' Full Biography
```json
{"function": "get_honoree", "slug": "michael-phelps", "include_content": true}
```

### List Recent Honorees
```json
{"function": "list_honorees", "page": 1, "per_page": 5}
```

### Search for Olympic Swimmers
```json
{"function": "search_honorees", "query": "olympic", "per_page": 20}
```

### Get Multiple Honorees by ID
```json
{"function": "list_honorees", "include_ids": "8143,6541", "include_content": true}
```

### Get All Masters Honorees
```json
{"function": "honorees_by_category", "category": "masters-honoree", "per_page": 100}
```

## Notes

- The API is public and requires no authentication
- Total database contains ~978 honorees
- Content includes detailed biographical information, achievements, and records
- Powered by WordPress REST API at `https://ishof.org/wp-json/wp/v2/`
- Images are available in multiple sizes via the `featured_image` field