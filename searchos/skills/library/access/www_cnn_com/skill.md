# CNN Heroes Profile Extractor

Extract biographical and profile data from CNN Hero pages with structured output.

## Overview

This skill provides reliable extraction of hero profile information from CNN's Heroes section, handling both modern CNN article format (with JSON-LD structured data) and legacy archive pages (using Open Graph metadata).

## Supported URL Patterns

- Modern articles: `https://www.cnn.com/YYYY/MM/DD/world/cnn-hero-of-the-year-YYYY`
- Modern articles: `https://www.cnn.com/YYYY/MM/DD/...cnn.*hero...`
- Legacy archive: `http://www.cnn.com/SPECIALS/cnn.heroes/archiveYY/name.html`

## Functions

### extract_profile

Extract comprehensive profile data from a single CNN Hero page.

**Parameters:**
- `url` (string, required): URL of the CNN Hero page

**Returns:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "url": "https://www.cnn.com/2017/12/17/world/amy-wright-2017-cnn-hero-of-the-year",
    "headline": "Advocate for disabled workers is 2017 CNN Hero of the Year",
    "description": "Amy Wright, who employs 40 people with disabilities...",
    "article_body": "Full article text...",
    "hero_name": "Amy Wright",
    "hero_year": "2017",
    "hero_type": "hero_of_the_year",
    "organization": "Bitty & Beau's Coffee",
    "images": [
      {
        "url": "https://media.cnn.com/...",
        "caption": "Amy Wright speaks onstage...",
        "credit": "Michael Loccisano/Getty Images for CNN"
      }
    ],
    "date_published": "2017-12-18T03:04:48Z",
    "date_modified": "2018-03-08T15:49:35Z",
    "author": "Melonyce McAfee",
    "source": "json-ld"
  }
}
```

**Example:**
```python
result = await execute({
    "function": "extract_profile",
    "url": "https://www.cnn.com/2017/12/17/world/amy-wright-2017-cnn-hero-of-the-year"
})
```

### extract_profiles

Extract profiles from multiple CNN Hero pages concurrently.

**Parameters:**
- `urls` (array, required): List of CNN Hero page URLs

**Returns:**
```json
{
  "success": true,
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "profiles": [
      {"success": true, "data": {...}},
      {"success": true, "data": {...}},
      {"success": true, "data": {...}}
    ]
  }
}
```

**Example:**
```python
result = await execute({
    "function": "extract_profiles",
    "urls": [
        "https://www.cnn.com/2015/11/17/world/cnn-hero-of-the-year-2015",
        "https://www.cnn.com/2017/12/17/world/amy-wright-2017-cnn-hero-of-the-year"
    ]
})
```

### check_urls

Quick accessibility check for CNN Hero page URLs.

**Parameters:**
- `urls` (array, required): List of URLs to check

**Returns:**
```json
{
  "success": true,
  "data": {
    "total": 2,
    "results": [
      {"url": "...", "status": 200, "error": null},
      {"url": "...", "status": 404, "error": null}
    ]
  }
}
```

## Extracted Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `hero_name` | string | Name of the CNN Hero |
| `hero_year` | string | Year of recognition (e.g., "2017") |
| `hero_type` | string | "hero_of_the_year" or "top_10_hero" |
| `headline` | string | Article headline |
| `description` | string | Brief description/summary |
| `article_body` | string | Full article text (truncated to 5000 chars) |
| `organization` | string | Associated organization/foundation name |
| `images` | array | List of images with url, caption, and credit |
| `date_published` | string | ISO 8601 publication date |
| `date_modified` | string | ISO 8601 modification date |
| `author` | string | Article author(s) |
| `source` | string | Data source: "json-ld" or "og-metadata" |

## Data Sources

The skill uses a prioritized extraction strategy:

1. **JSON-LD (preferred)**: Modern CNN articles contain structured NewsArticle data in JSON-LD format, providing the most comprehensive information including full article body and metadata.

2. **Open Graph metadata**: Fallback for pages without JSON-LD, extracting title, description, and basic metadata from OG tags.

3. **Pattern extraction**: Hero name, year, and type are extracted using regex patterns from combined text sources.

## Error Handling

All functions return structured error responses:

```json
{
  "success": false,
  "error": "HTTP error: 404",
  "data": null
}
```

Common errors:
- `Missing required parameter: url` or `Missing required parameter: urls`
- `Invalid URL format`
- `HTTP error: 404` (page not found)
- `Request timeout` (timeout after 45 seconds)
- `Network error: ...` (connection issues)

## Notes

- **No authentication required**: Uses public HTTP requests
- **Rate limiting**: Recommends 2 requests/second, 30 requests/minute
- **Timeout**: 45 seconds per request
- **Legacy pages**: Archive pages (archive10, etc.) have less structured data available

## Tested URLs

The skill has been verified with:
- `http://www.cnn.com/SPECIALS/cnn.heroes/archive10/anuradha.koirala.html` (2010 Top 10 Hero)
- `https://www.cnn.com/2015/11/17/world/cnn-hero-of-the-year-2015` (2015 Hero of the Year)
- `https://www.cnn.com/2017/12/17/world/amy-wright-2017-cnn-hero-of-the-year` (2017 Hero of the Year)

## Technical Details

- Uses `aiohttp` for async HTTP requests
- Uses `BeautifulSoup4` for HTML parsing
- Handles both HTTP and HTTPS URLs
- Follows redirects automatically
- User-Agent header included for compatibility