# PitchBook Company Profile Access Skill

Access company profile data from PitchBook, including founded date, status, employees, deals, and funding information.

## Overview

PitchBook (pitchbook.com) is a comprehensive database for private market data, including companies, investors, deals, and funds. This skill provides programmatic access to PitchBook company profiles.

## Features

- **Company Profile Extraction**: Retrieve key company data including:
  - Company name and description
  - Founded year
  - Employee count
  - Company status (Private/Public)
  - Headquarters location
  - Website
  - Industry/Sector
  - Revenue and Valuation (when available)
  - Deal history

- **Multiple Access Methods**:
  - Direct URL access
  - Company ID lookup
  - Authenticated session support (via cookies)

- **Cloudflare Handling**:
  - Automatic detection of Cloudflare challenges
  - Configurable wait times
  - Graceful fallbacks when blocked

## Configuration

### Required Parameter
- `url`: PitchBook company profile URL or company ID
  - Full URL: `https://pitchbook.com/profiles/company/123241-33`
  - Or just the ID: `123241-33`

### Optional Parameters
- `cookies`: List of cookies for authenticated access (see below)
- `headless`: Run browser in headless mode (default: `true`)
- `max_wait`: Maximum seconds to wait for page load (default: `40`)

## Authentication

### Why Authentication Matters

PitchBook has two access barriers:
1. **Cloudflare Protection**: Blocks automated browser access
2. **Subscription Requirement**: Full profile data requires a paid subscription

### Using Authenticated Cookies

To access full profile data, provide cookies from an authenticated browser session:

```python
result = await execute({
    "function": "get_profile",
    "url": "https://pitchbook.com/profiles/company/123241-33",
    "cookies": [
        {
            "name": "session_id",
            "value": "your_session_value",
            "domain": ".pitchbook.com"
        },
        {
            "name": "auth_token",
            "value": "your_auth_token",
            "domain": ".pitchbook.com"
        }
    ]
})
```

### Extracting Cookies from Browser

1. Log into PitchBook in your browser
2. Open Developer Tools (F12)
3. Go to Application > Cookies > https://pitchbook.com
4. Copy relevant cookies (especially authentication cookies)

## Usage Examples

### Basic Profile Lookup

```python
from executor import execute

result = await execute({
    "function": "get_profile",
    "url": "https://pitchbook.com/profiles/company/123241-33"
})

if result["success"]:
    print(f"Company: {result['data'].get('company_name')}")
    print(f"Founded: {result['data'].get('founded')}")
    print(f"Employees: {result['data'].get('employees')}")
else:
    print(f"Error: {result['error']}")
    print(result['message'])
```

### Using Company ID Only

```python
result = await execute({
    "function": "get_profile",
    "url": "135027-28"
})
```

### With Extended Wait Time

```python
result = await execute({
    "function": "get_profile",
    "url": "https://pitchbook.com/profiles/company/123241-33",
    "max_wait": 60
})
```

## Response Structure

### Successful Response

```json
{
    "success": true,
    "company_id": "123241-33",
    "url": "https://pitchbook.com/profiles/company/123241-33",
    "data": {
        "company_name": "Example Startup Inc.",
        "founded": "2015",
        "employees": "50-100",
        "status": "Private",
        "headquarters": "San Francisco, CA",
        "website": "https://example.com",
        "industry": "Software / SaaS",
        "revenue": "$10M",
        "valuation": "$100M",
        "deals": [
            {"year": "2023", "amount": "$20M", "type": "Series B"},
            {"year": "2021", "amount": "$5M", "type": "Series A"}
        ]
    }
}
```

### Error Response

```json
{
    "success": false,
    "error": "cloudflare_blocked",
    "message": "Cloudflare challenge not passed...",
    "company_id": "123241-33",
    "url": "https://pitchbook.com/profiles/company/123241-33",
    "suggestions": [
        "Use authenticated session cookies from a logged-in browser",
        "Try again later",
        "Consider using a different IP address"
    ]
}
```

## Error Types

| Error | Description | Solution |
|-------|-------------|----------|
| `missing_function` | No function specified | Include `function: "get_profile"` |
| `unknown_function` | Invalid function name | Use `get_profile` |
| `missing_url` | No URL provided | Include `url` parameter |
| `invalid_url` | URL format is invalid | Use valid PitchBook URL or ID |
| `browser_error` | Browser failed to initialize | Check Playwright installation |
| `cloudflare_blocked` | Cloudflare challenge not passed | Use authenticated cookies |
| `subscription_required` | Login wall detected | Log in with PitchBook account |
| `execution_error` | General execution error | Check error message |

## Limitations

1. **Cloudflare Protection**: PitchBook uses aggressive anti-bot protection that may block access
2. **Subscription Required**: Full profile data requires a paid PitchBook subscription
3. **Rate Limiting**: Excessive requests may trigger IP blocks
4. **Data Availability**: Not all companies have complete profiles

## Requirements

- Python 3.11+
- Playwright (`pip install playwright && playwright install chromium`)

## Technical Notes

### Browser Automation

This skill uses Playwright for browser automation with anti-detection measures:
- User agent spoofing
- WebDriver property masking
- JavaScript execution environment modifications

### Cloudflare Challenge

The skill waits for Cloudflare challenges to complete before extracting data. If the challenge persists beyond the wait time, it returns an error with suggestions.

### Data Extraction

Data is extracted using multiple methods:
- DOM parsing for visible content
- JSON-LD structured data
- Next.js `__NEXT_DATA__` props
- Meta tag extraction

## Troubleshooting

### "Cloudflare blocked" error

1. Wait a few minutes and try again
2. Use authenticated cookies from a logged-in session
3. Consider using a residential proxy
4. Try accessing from a different IP address

### "Playwright not available" error

```bash
pip install playwright
playwright install chromium
```

### Empty data returned

- The profile may be behind a login wall
- Try with authenticated cookies
- Check if the company ID is valid

## Support

For issues or feature requests, please open an issue on the SearchOS repository.