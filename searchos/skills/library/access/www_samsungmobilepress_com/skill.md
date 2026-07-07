# Samsung Mobile Press Access Skill

Extract device specifications from Samsung Mobile Press (www.samsungmobilepress.com).

## Overview

Samsung Mobile Press is Samsung's official press resource site for mobile devices. It hosts detailed technical specifications for Galaxy smartphones, tablets, wearables, and related accessories.

### Why Playwright?

The site uses Next.js with server-side rendering. Specification data is embedded in HTML tables that require browser rendering to access. The generic web reader often fails to render the dynamic tab content (specs tab), returning empty results. This skill uses Playwright to:

1. Load the page with the specs tab active (`?tab=specs`)
2. Wait for the table to render
3. Parse the HTML table structure
4. Extract structured specification data

## Functions

### `get_specs`

Get detailed specifications for a specific Samsung device.

**Parameters:**
- `slug` (required): Device identifier from the URL (e.g., `galaxy-s24`, `galaxy_note20`)

**Example:**
```json
{
  "function": "get_specs",
  "slug": "galaxy-s24"
}
```

**Response:**
```json
{
  "success": true,
  "device": "Galaxy S24",
  "slug": "galaxy-s24",
  "url": "https://www.samsungmobilepress.com/media-assets/galaxy-s24?tab=specs",
  "specs_count": 8,
  "specs": [
    {
      "category": "Display",
      "value": "6.2-inch FHD+ | Dynamic AMOLED 2X Display | Super Smooth 120Hz..."
    },
    {
      "category": "Camera",
      "value": "12MP Ultra-Wide Camera | F2.2, FOV 120˚ | 50MP Wide Camera..."
    }
  ]
}
```

### `search`

Search for devices by name or keyword.

**Parameters:**
- `query` (required): Search term (e.g., `galaxy`, `s24`, `note`)
- `limit` (optional): Maximum results (default: 20)

**Example:**
```json
{
  "function": "search",
  "query": "fold"
}
```

### `list`

List common Galaxy device slugs known to exist on Samsung Mobile Press.

**Example:**
```json
{
  "function": "list"
}
```

**Response:**
```json
{
  "success": true,
  "total": 22,
  "devices": [
    {"slug": "galaxy-s24", "name": "Galaxy S24", "series": "Galaxy S"},
    {"slug": "galaxy-s24-ultra", "name": "Galaxy S24 Ultra", "series": "Galaxy S"},
    {"slug": "galaxy-z-fold6", "name": "Galaxy Z Fold6", "series": "Galaxy Z"}
  ]
}
```

## Supported Devices

Common device slugs include:

**Galaxy S Series:**
- `galaxy-s24`, `galaxy-s24-plus`, `galaxy-s24-ultra`
- `galaxy-s22`, `galaxy-s22-plus`, `galaxy-s22-ultra`

**Galaxy Z Series:**
- `galaxy-z-fold6`, `galaxy-z-fold5`, `galaxy-z-fold4`
- `galaxy-z-flip6`, `galaxy-z-flip5`, `galaxy-z-flip4`

**Galaxy Note Series:**
- `galaxy_note20`, `galaxy-note20-ultra`

**Galaxy A Series:**
- `galaxy-a55-5g`, `galaxy-a35-5g`

**Wearables:**
- `galaxy-watch7`, `galaxy-watch6`
- `galaxy-buds3-pro`, `galaxy-buds2-pro`

**Tablets:**
- `galaxy-tab-s10-plus`, `galaxy-tab-s9`

## Data Structure

Specifications are returned as an array of category-value pairs. Categories commonly include:

- Display
- Camera
- Dimensions & Weight
- Memory & Storage
- Battery
- Charging
- OS (Operating System)
- AP (Application Processor)
- Security
- Water Resistance
- Network
- Connectivity
- S Pen (for Note devices)

Values may contain multiple specifications separated by ` | ` characters. Footnotes and disclaimers are included but prefixed footnote markers are stripped.

## Output Format

Each specification category is extracted as:
```json
{
  "category": "Display",
  "value": "6.2-inch FHD+ | Dynamic AMOLED 2X Display | Super Smooth 120Hz refresh rate"
}
```

Values are cleaned to remove excessive whitespace while preserving technical details.

## Implementation Notes

1. **Table Parsing:** Different devices use different table structures (colspan, rowspan, nested cells). The extractor handles multiple formats.

2. **Specs Tab:** URLs must include `?tab=specs` to automatically display the specifications tab.

3. **Older Devices:** Some older devices (e.g., Galaxy Note20) have more detailed specs tables with additional categories like S Pen.

4. **Rate Limiting:** Be considerate when making multiple requests. The skill includes reasonable timeouts and network idle waiting.

## Dependencies

- `playwright>=1.40.0` - Browser automation for JavaScript rendering

## Limitations

- Requires browser automation (Playwright), not a pure HTTP API solution
- Some very new or very old devices may not have specs pages
- Specification format varies between device generations
- Search function requires the media assets page to be rendered