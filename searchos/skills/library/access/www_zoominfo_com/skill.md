# ZoomInfo Access Skill

## Overview

This skill provides access to ZoomInfo's public pages and company profile data. 

**Important Limitations**: ZoomInfo employs aggressive bot detection (PerimeterX and Cloudflare), which blocks most automated access to company profile pages (`/c/` URLs). While public pages like `/about` and `/blog` are accessible, individual company profiles will typically return `403 Forbidden` or `429 Too Many Requests`.

## Available Functions

### 1. `get_public_page`

Fetches public ZoomInfo pages that don't require authentication.

**Parameters:**
- `url` (required): Full ZoomInfo URL (e.g., `https://www.zoominfo.com/about`)

**Known public pages:**
- `https://www.zoominfo.com/about` - Company information
- `https://www.zoominfo.com/blog` - B2B sales and marketing blog

**Example:**
```json
{
  "function": "get_public_page",
  "url": "https://www.zoominfo.com/about"
}
```

**Returns:**
- Page title and meta description
- JSON-LD structured data
- Next.js page data (if available)
- Page content preview

### 2. `get_company_profile`

Attempts to fetch a company profile from ZoomInfo.

**Parameters:**
- `url` (optional): Full ZoomInfo company profile URL
- `company_id` (optional): ZoomInfo company ID (numeric)
- `company_name` (optional): Company name (used to construct URL slug)

**Note:** At least one of `url` or `company_id` is required.

**Example:**
```json
{
  "function": "get_company_profile",
  "url": "https://www.zoominfo.com/c/hawthorne-residential-partners-llc/348143237"
}
```

**Returns:**
- Status code (likely `403` or `429` due to bot protection)
- Blocked reason (if blocked)
- Company ID and slug extracted from URL

### 3. `search_companies`

Returns search engine URLs for finding ZoomInfo company profiles via cache.

**Parameters:**
- `query` (required): Company name or keywords to search

**Example:**
```json
{
  "function": "search_companies",
  "query": "Hawthorne Residential Partners"
}
```

**Returns:**
- Search engine URLs (Google, Bing, DuckDuckGo)
- Possible ZoomInfo URL patterns
- Tips for finding cached pages

### 4. `get_sitemap`

Retrieves ZoomInfo's sitemap to discover publicly listed URLs.

**Parameters:** None

**Example:**
```json
{
  "function": "get_sitemap"
}
```

**Returns:**
- List of sitemap URLs (e.g., careers, case studies, leadership)
- Helpful for discovering publicly accessible content

## Bot Detection

ZoomInfo uses multiple layers of bot protection:

1. **PerimeterX**: JavaScript-based bot detection
2. **Cloudflare**: Rate limiting and WAF rules
3. **CAPTCHA**: Appears on suspicious requests

### What Works
- Public pages (`/about`, `/blog`, `/company`)
- Sitemaps and meta information
- Static assets

### What Doesn't Work
- Company profile pages (`/c/`)
- Search functionality
- Any authenticated endpoints

## Alternatives for Company Data

Since ZoomInfo profiles are blocked, consider these alternatives:

1. **Search Engine Cache**: Use the `search_companies` function to get search URLs
2. **LinkedIn**: Many companies have LinkedIn profiles with similar data
3. **Crunchbase**: Good for startup/company information
4. **Official Company Websites**: Often have "About" pages

## Response Formats

All functions return structured JSON with these common fields:

```json
{
  "url": "requested URL",
  "status": 200,  // HTTP status code
  "title": "Page title",
  "meta_description": "Page description",
  "json_ld": [...],  // Structured data
  "next_data": {...},  // Next.js page data
  "blocked_reason": "bot_detection_perimeterx",  // If blocked
  "error": "error_type",  // If error
  "message": "Error message"
}
```

## Technical Details

- Uses `httpx` for HTTP requests (better TLS/HTTP2 handling)
- Parses HTML with `BeautifulSoup`
- Extracts JSON-LD and Next.js data
- Retries with different user agents (for company profiles)
- Respects rate limits

## Rate Limiting

The skill includes built-in delays between requests when trying multiple user agents. Even so, you may encounter:

- **429 Too Many Requests**: Back off and retry later
- **403 Forbidden**: Bot detection triggered
- **CAPTCHA**: Cannot be solved automatically

## Examples

### Get About Page
```python
result = await execute({
    "function": "get_public_page",
    "url": "https://www.zoominfo.com/about"
})
# Returns: title, description, Next.js data with company stats
```

### Attempt Company Profile (Expected to Fail)
```python
result = await execute({
    "function": "get_company_profile",
    "url": "https://www.zoominfo.com/c/example-company/123456789"
})
# Returns: status 403/429, blocked_reason
```

### Find Search Alternatives
```python
result = await execute({
    "function": "search_companies",
    "query": "Example Company Inc"
})
# Returns: Google/Bing search URLs with site:zoominfo.com/c filter
```