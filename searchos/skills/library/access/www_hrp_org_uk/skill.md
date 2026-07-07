# Historic Royal Palaces (HRP) Access Skill

This skill provides access to opening times and ticket prices from the Historic Royal Palaces website (www.hrp.org.uk).

## Features

- **List Palaces**: Get a list of all available Historic Royal Palace properties
- **Opening Times**: Retrieve current opening and closing times for any HRP palace
- **Ticket Prices**: Get current ticket pricing information for any HRP palace
- **Fallback Data**: Includes sample data when Cloudflare blocks automated access

## Available Palaces

The skill supports the following Historic Royal Palaces properties:

1. **Tower of London** (`tower-of-london`)
2. **Hampton Court Palace** (`hampton-court-palace`)
3. **Kensington Palace** (`kensington-palace`)
4. **Banqueting House** (`banqueting-house`)
5. **Kew Palace** (`kew-palace`)
6. **Hillsborough Castle** (`hillsborough-castle`)

## Usage Examples

### List All Palaces
```python
result = await execute({
    'function': 'list_palaces'
}, context)
```

Returns a list of all available palaces with their IDs and URLs.

### Get Opening Times (Live Data)
```python
result = await execute({
    'function': 'get_opening_times',
    'palace': 'tower-of-london'
}, context)
```

Attempts to fetch live data from the website. If blocked by Cloudflare, returns sample data as fallback.

### Get Opening Times (Sample Data)
```python
result = await execute({
    'function': 'get_opening_times',
    'palace': 'kensington-palace',
    'use_sample': True
}, context)
```

Returns sample data without attempting to access the website (avoids Cloudflare blocks).

### Get Ticket Prices
```python
result = await execute({
    'function': 'get_ticket_prices',
    'palace': 'kensington-palace'
}, context)

# Or with sample data
result = await execute({
    'function': 'get_ticket_prices',
    'palace': 'hampton-court-palace',
    'use_sample': True
}, context)
```

## Cloudflare Protection

The HRP website is protected by Cloudflare's security system, which blocks most automated access. This skill implements several strategies:

1. **Persistent Browser Context**: Uses a persistent browser session to maintain cookies
2. **Extended Wait Times**: Configurable wait time to allow challenge resolution
3. **Proper Headers**: Includes realistic browser headers
4. **Fallback Data**: Returns sample data when live access fails
5. **Sample Data Mode**: Option to bypass live fetch entirely with `use_sample=true`

## Response Structure

### Success Response (Live Data)
```json
{
  "success": true,
  "palace": "tower-of-london",
  "url": "https://www.hrp.org.uk/tower-of-london/visit/opening-and-closing-times/",
  "opening_times": [...],
  "last_admission": {...},
  "special_closures": [...],
  "data_source": "live"
}
```

### Success Response (Sample Data)
```json
{
  "success": true,
  "palace": "tower-of-london",
  "url": "https://www.hrp.org.uk/tower-of-london/visit/opening-and-closing-times/",
  "opening_times": [...],
  "last_admission": {...},
  "data_source": "sample",
  "note": "This is sample data..."
}
```

### Response with Fallback
```json
{
  "success": false,
  "error": "HTTP 403",
  "palace": "tower-of-london",
  "fallback_data": {
    "opening_times": [...],
    "last_admission": {...}
  },
  "note": "The site is protected by Cloudflare. Sample data provided as fallback.",
  "website_note": "For the most current information, please visit the official website directly."
}
```

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `function` | string | Yes | - | Function to call: `list_palaces`, `get_opening_times`, or `get_ticket_prices` |
| `palace` | string | No | `"tower-of-london"` | Palace identifier (e.g., `tower-of-london`, `kensington-palace`) |
| `max_wait` | integer | No | `45` | Maximum seconds to wait for Cloudflare challenge resolution |
| `use_sample` | boolean | No | `false` | If true, returns sample data without live fetch |

## Sample Data Disclaimer

Sample data included in this skill is approximate and may not reflect current prices or opening times. Always verify current information at https://www.hrp.org.uk/ before making travel plans.

## Technical Details

- **Implementation**: Uses Playwright with Chromium for browser automation
- **Parsing**: BeautifulSoup for HTML parsing and data extraction
- **Session Management**: Persistent browser context for cookie persistence
- **Fallback**: Sample data returned when Cloudflare blocks access
- **Error Handling**: Comprehensive error reporting with fallback data

## Official Website

For the most up-to-date information, visit: https://www.hrp.org.uk/