# NatureScot Access Skill

## Overview

This skill provides programmatic access to NatureScot (www.nature.scot), the Scottish government's nature conservation agency website. It retrieves protected area designations, commissioned reports, and environmental research publications.

## Important Notes

### Cloudflare Protection

NatureScot uses **Cloudflare protection** that blocks automated access from:
- Bots and web scrapers
- Automated HTTP clients
- Headless browsers without proper configuration

This is a **known limitation** and the skill is designed to:
1. Attempt access with multiple user agents
2. Detect and report Cloudflare blocks
3. Provide diagnostic information
4. Fall back to browser-based access if Playwright is available

## Available Functions

### 1. `fetch_page`

Fetches a single page from NatureScot.

**Parameters:**
- `url` (required): Full URL of the page to fetch
- `use_browser` (optional): Boolean, whether to use browser-based access (default: false)
- `timeout` (optional): Timeout in seconds (default: 30)

**Example:**
```json
{
  "function": "fetch_page",
  "url": "https://www.nature.scot/professional-advice/protected-areas-and-species/protected-areas/national-designations/national-scenic-areas"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "...",
  "title": "Page Title",
  "html": "<html>...</html>",
  "body_text": "...",
  "headings": [...],
  "links": [...],
  "tables": [...],
  "metadata": {...}
}
```

### 2. `check_access_health`

Checks the current accessibility status of the NatureScot website.

**Parameters:**
- `timeout` (optional): Timeout in seconds (default: 30)

**Example:**
```json
{
  "function": "check_access_health"
}
```

**Returns:**
```json
{
  "timestamp": 1234567890.123,
  "site_accessible": false,
  "simple_http": {"success": false, "status": 403},
  "browser_access": {"success": false, "error": "..."},
  "cloudflare_active": true,
  "recommendations": [...]
}
```

## Content Types Available

When access is successful, the following content can be retrieved:

### Protected Areas
- National Scenic Areas (NSAs)
- Sites of Special Scientific Interest (SSSIs)
- Special Areas of Conservation (SACs)
- Special Protection Areas (SPAs)
- National Nature Reserves (NNRs)

### Publications
- Commissioned Reports
- Research publications
- Guidance documents
- Policy papers

### Professional Advice
- Protected species guidance
- Development planning advice
- Licensing information
- Management guidance

## Troubleshooting

### If you get a Cloudflare block:

1. **Wait and retry**: The block may be temporary
2. **Use browser mode**: Set `use_browser: true` (requires Playwright)
3. **Check health**: Run `check_access_health` first
4. **Manual access**: The site works normally in a regular browser

### Alternative data sources:

If automated access continues to fail, consider:
- Scottish Government Open Data Portal
- UK Government data services
- Direct contact with NatureScot for data requests

## Technical Details

### Dependencies
- **aiohttp**: For HTTP requests (required)
- **playwright**: For browser-based access (optional)

### Rate Limiting
The skill implements rate limiting (1 request/second minimum) to be respectful to the server.

### User Agents
The skill tries multiple user agents in order:
1. Google bot
2. Bing bot
3. Standard Chrome browser
4. Firefox browser

## Known URLs

### Test URLs
- National Scenic Areas: `/professional-advice/protected-areas-and-species/protected-areas/national-designations/national-scenic-areas`
- Commissioned Report 374: `/doc/naturescot-commissioned-report-374-special-qualities-national-scenic-areas`

### Common Paths
- `/professional-advice/` - Professional advice and guidance
- `/doc/` - Documents and commissioned reports
- `/protected-areas/` - Protected area information
- `/species/` - Species guidance

## Limitations

1. **Cloudflare blocks most automated access** - This is the primary limitation
2. **No API access** - NatureScot does not provide a public API
3. **Rate limiting** - Even when access works, requests must be limited
4. **Content variability** - Site structure may change over time

## Future Improvements

Potential enhancements if access becomes reliable:
- Search functionality
- Publication listing and filtering
- Protected area database queries
- Species information retrieval
- Document download handling