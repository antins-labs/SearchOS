# Britannica Biography Access Skill

Access biography and encyclopedia pages from Britannica.com with structured data extraction and robust protection handling.

## Overview

This skill fetches pages from Britannica.com and extracts structured biography data including:
- Names and titles
- Birth and death dates
- Nationality and profession
- Notable works
- Summary descriptions
- Quick facts
- JSON-LD structured data

## Features

- **Anti-bot Protection Handling**: Uses advanced techniques to bypass Cloudflare challenges
- **Structured Data Extraction**: Automatically extracts key biography information
- **Flexible Search**: Search by name to find biography URLs
- **Error Handling**: Graceful handling of blocks, timeouts, and missing content
- **Content Preview**: Returns first paragraph of biography content

## Functions

### fetch

Fetches a Britannica URL and extracts structured biography data.

**Parameters:**
- `url` (required): The Britannica URL to fetch
- `max_wait` (optional): Maximum seconds to wait for content (default: 60)

**Example:**
```python
result = await execute({
    'function': 'fetch',
    'url': 'https://www.britannica.com/biography/Alice-Munro',
    'max_wait': 60
})
```

**Returns:**
```json
{
  "success": true,
  "title": "Alice Munro | Biography, Books, & Facts | Britannica",
  "heading": "Alice Munro",
  "description": "Alice Munro, Canadian short-story writer...",
  "quick_facts": {
    "Born": "July 10, 1931, Wingham, Ontario, Canada",
    "Died": "May 13, 2024, Port Hope, Ontario, Canada",
    "Nationality": "Canadian"
  },
  "content_preview": "Alice Munro (born July 10, 1931, Wingham, Ontario, Canada—died May 13, 2024, Port Hope, Ontario, Canada) was a Canadian short-story writer...",
  "notable_works": ["Dance of the Happy Shades", "Lives of Girls and Women", "..."],
  "json_ld": {...},
  "url": "https://www.britannica.com/biography/Alice-Munro",
  "final_url": "https://www.britannica.com/biography/Alice-Munro"
}
```

### search

Searches for a biography by name and returns matching URLs.

**Parameters:**
- `name` (required): The name of the person to search for

**Example:**
```python
result = await execute({
    'function': 'search',
    'name': 'Alice Munro'
})
```

**Returns:**
```json
{
  "success": true,
  "query": "Alice Munro",
  "search_url": "https://www.britannica.com/search?query=Alice+Munro",
  "results": [
    {
      "url": "https://www.britannica.com/biography/Alice-Munro",
      "title": "Alice Munro",
      "type": "biography"
    }
  ],
  "best_match": {
    "url": "https://www.britannica.com/biography/Alice-Munro",
    "title": "Alice Munro",
    "type": "biography"
  },
  "total_results": 1
}
```

## Cloudflare Protection

Britannica.com uses aggressive Cloudflare protection that may block automated access. This skill includes:

- Anti-fingerprinting techniques
- Realistic browser headers
- Extended wait periods for challenge resolution
- Clear error messages when access is blocked

If you receive a `CLOUDFLARE_BLOCK` error, try:
- Waiting a few minutes before retrying
- Using a different IP address
- Reducing request frequency

## Error Handling

The skill returns structured error responses instead of raising exceptions:

```json
{
  "success": false,
  "error": "Cloudflare challenge not resolved. The site is blocking automated access.",
  "error_code": "CLOUDFLARE_BLOCK",
  "url": "https://www.britannica.com/biography/Alice-Munro",
  "hint": "Try again later or from a different IP address."
}
```

**Common Error Codes:**
- `CLOUDFLARE_BLOCK`: Site blocked automated access
- `TIMEOUT`: Request timed out
- `MISSING_PARAM`: Required parameter missing
- `INVALID_URL`: URL not from britannica.com domain
- `SEARCH_BLOCKED`: Search page not accessible

## Supported URLs

This skill works with:
- Biography pages: `https://www.britannica.com/biography/{name}`
- Place pages: `https://www.britannica.com/place/{name}`
- Topic pages: `https://www.britannica.com/topic/{name}`
- Other Britannica encyclopedia pages

## Technical Notes

- Uses Playwright with Chromium browser
- Implements anti-detection measures
- Waits for Cloudflare challenges to resolve (up to 60 seconds by default)
- Extracts both structured (JSON-LD) and unstructured (HTML) data
- Returns comprehensive error information for debugging

## Limitations

- Cloudflare protection may prevent access completely in some cases
- Long wait times may be needed for challenge resolution
- Some pages may have different structures that aren't fully parsed
- Rate limiting may apply from Britannica's servers