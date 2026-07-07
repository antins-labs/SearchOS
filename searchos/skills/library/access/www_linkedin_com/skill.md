# LinkedIn Company Page Access Skill

Access company profile information from LinkedIn with robust error handling for access restrictions.

## Overview

This skill fetches company data from LinkedIn company pages while handling the platform's strict access controls:
- **Geo-restrictions** (HTTP 451): LinkedIn redirects to regional sites
- **Authentication walls**: Company data often requires login
- **Bot detection** (HTTP 999): Automated access is blocked

## Functions

### get_company_info

Fetches company profile data from a LinkedIn company page.

**Parameters:**
- `url` (string, optional): LinkedIn company page URL
- `slug` (string, optional): Company identifier (alternative to URL)

**Returns:**
```json
{
  "success": true,
  "slug": "proudlypeakmade",
  "url": "https://www.linkedin.com/company/proudlypeakmade",
  "data": {
    "name": "Company Name",
    "description": "Company description",
    "website": "https://company.com",
    "og_title": "...",
    "og_description": "..."
  }
}
```

**Error responses include:**
- `GEO_RESTRICTED`: Access blocked due to geographic restrictions
- `BOT_DETECTED`: LinkedIn blocked automated access
- `AUTH_REQUIRED`: Page loaded but data requires authentication
- `ACCESS_FAILED`: General access failure with detailed message

### extract_slug

Extracts the company slug from a LinkedIn URL.

**Parameters:**
- `url` (string): LinkedIn company page URL

**Returns:**
```json
{
  "success": true,
  "slug": "company-name",
  "url": "https://www.linkedin.com/company/company-name/about",
  "normalized_url": "https://www.linkedin.com/company/company-name"
}
```

## Usage Examples

### Example 1: Get company info from URL

```python
result = await execute({
    "function": "get_company_info",
    "url": "https://www.linkedin.com/company/proudlypeakmade"
})
```

### Example 2: Get company info using slug

```python
result = await execute({
    "function": "get_company_info",
    "slug": "fpi-management-inc"
})
```

### Example 3: Extract slug from URL

```python
result = await execute({
    "function": "extract_slug",
    "url": "https://www.linkedin.com/company/google/about"
})
# Returns: {"success": true, "slug": "google", ...}
```

## Known Limitations

LinkedIn enforces strict access controls that may prevent data extraction:

1. **Geographic Restrictions**: Access from certain regions redirects to linkedin.cn with HTTP 451
2. **Bot Detection**: Automated requests receive HTTP 999 responses
3. **Authentication Required**: Even when pages load, company data often requires login
4. **Rate Limiting**: Frequent requests are blocked

## Error Handling

All functions return structured error responses instead of raising exceptions:

```python
{
    "success": false,
    "error": "Human-readable error message",
    "error_code": "ERROR_CODE",
    "status": 451,
    "slug": "company-slug",
    "url": "https://...",
    "message": "Detailed explanation and suggestions",
    "known_limitations": [...],
    "suggestions": [...]
}
```

## Alternative Approaches

When this skill cannot access data due to restrictions, consider:

1. **LinkedIn Official API**: Requires developer credentials and OAuth
2. **LinkedIn Data Partners**: Official data providers with API access
3. **Manual Access**: Direct browser access from permitted regions
4. **Alternative Sources**: Other business data providers (Crunchbase, PitchBook, etc.)

## Technical Details

- Uses `aiohttp` for async HTTP requests
- Attempts multiple fetch strategies (direct, no-redirects)
- Parses JSON-LD structured data when available
- Extracts Open Graph metadata as fallback
- Handles various LinkedIn URL formats:
  - `/company/{slug}`
  - `/company-beta/{slug}`
  - `/showcase/{slug}`
  - `/school/{slug}`