# Simple Wikipedia Award Data Access Skill

Extract structured award recipient data from Simple Wikipedia (simple.wikipedia.org).

## Overview

This skill provides access to award pages on Simple Wikipedia, automatically parsing winner lists in the common format:

```
2025 - Doechii for Alligator Bites Never Heal
2024 - Killer Mike for Michael
...
```

## Functions

### `get_award_page`

Fetch and parse a complete award page.

**Parameters:**
- `title` (required): Wikipedia page title (use underscores for spaces)
- `include_html` (optional): Include parsed HTML content (default: false)

**Example:**
```python
result = execute({
    "function": "get_award_page",
    "title": "Grammy_Award_for_Best_Rap_Album"
})
```

**Returns:**
```python
{
    "success": True,
    "page": {
        "page_id": 652938,
        "title": "Grammy Award for Best Rap Album",
        "url": "https://simple.wikipedia.org/wiki/Grammy_Award_for_Best_Rap_Album",
        "categories": ["Grammy Awards", "Rap music"]
    },
    "winners": [
        {"year": 2025, "artist": "Doechii", "album": "Alligator Bites Never Heal"},
        {"year": 2024, "artist": "Killer Mike", "album": "Michael"},
        # ... more winners
    ],
    "winner_count": 30,
    "introduction": "The Grammy Award for Best Rap Album has been awarded since 1996...",
    "year_range": {
        "first": 1996,
        "latest": 2025
    }
}
```

### `get_winners`

Extract winners with filtering options.

**Parameters:**
- `title` (required): Wikipedia page title
- `year` (optional): Filter by specific year
- `limit` (optional): Maximum number of results
- `sort` (optional): Sort order - "desc" (newest first) or "asc" (oldest first)

**Example:**
```python
# Get recent winners
result = execute({
    "function": "get_winners",
    "title": "Grammy_Award_for_Best_Rap_Album",
    "limit": 5
})

# Get winner for specific year
result = execute({
    "function": "get_winners",
    "title": "Grammy_Award_for_Best_Rap_Album",
    "year": 2020
})
```

### `search_awards`

Search for award pages on Simple Wikipedia.

**Parameters:**
- `query` (required): Search term
- `limit` (optional): Maximum results (default: 20)

**Example:**
```python
result = execute({
    "function": "search_awards",
    "query": "Grammy Award"
})
```

**Returns:**
```python
{
    "success": True,
    "query": "Grammy Award",
    "results": [
        {
            "title": "Grammy Award for Best Rap Album",
            "description": "Award for rap albums",
            "url": "https://simple.wikipedia.org/wiki/Grammy_Award_for_Best_Rap_Album"
        },
        # ... more results
    ],
    "count": 10
}
```

## Data Format

### Winner Object
```python
{
    "year": int,      # Award year (e.g., 2025)
    "artist": str,    # Artist/recipient name
    "album": str      # Album/work title (cleaned of suffixes like "(album)")
}
```

## Use Cases

- **Historical award data**: Retrieve complete winner lists for award categories
- **Year-specific lookups**: Find who won in a specific year
- **Award comparisons**: Compare winners across categories
- **Data enrichment**: Supplement other data sources with award information

## API Details

This skill uses the Simple Wikipedia MediaWiki API:
- Endpoint: `https://simple.wikipedia.org/w/api.php`
- Actions used: `query`, `parse`, `opensearch`
- Response format: JSON
- No authentication required

## Limitations

1. **Content availability**: Only works with pages that exist on Simple Wikipedia
2. **Data format**: Requires award data in list format; table-based pages are not supported
3. **Simple Wikipedia**: Uses simplified content; for more detailed data, use the full Wikipedia API

## Error Handling

All errors are returned with consistent structure:

```python
{
    "success": False,
    "error": "Description of the error",
    "error_code": "ERROR_CODE"
}
```

**Error codes:**
- `MISSING_PARAM`: Required parameter missing
- `NOT_FOUND`: Page does not exist
- `TIMEOUT`: Request timed out
- `HTTP_ERROR`: HTTP error occurred
- `INTERNAL_ERROR`: Unexpected error

## Rate Limits

Simple Wikipedia has general rate limits:
- Recommended: 10 requests per second
- Burst: Up to 20 requests

The skill includes proper User-Agent identification and follows API best practices.

## Example Pages

Known award pages on Simple Wikipedia:
- `Grammy_Award_for_Best_Rap_Album`
- `Academy_Award_for_Best_Picture`
- `Academy_Award_for_Best_Actor`
- `Academy_Award_for_Best_Actress`
- `Grammy_Award_for_Album_of_the_Year`

Use `search_awards` to discover more award pages.