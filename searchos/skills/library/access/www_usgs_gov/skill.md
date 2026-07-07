# USGS.gov Scientific Data Access Skill

Extract structured scientific data from the U.S. Geological Survey website, including national park geology information, volcano observatory data, eruption alerts, and research program details.

## Overview

The USGS website (www.usgs.gov) contains authoritative scientific information about:
- **National Park Geology**: Detailed geological history, formations, and processes for parks across the United States
- **Volcano Observatories**: Real-time volcano status, alerts, monitoring data, and eruption updates
- **Research Programs**: Information about USGS science programs, data products, and research initiatives

Due to AWS WAF protection with CAPTCHA verification, this skill uses browser automation (Playwright) with anti-detection measures for reliable access.

## Features

### Page Type Detection
Automatically detects and extracts appropriate data from:
- National park geology pages (structured history, formations, media)
- Volcano observatory pages (status, alerts, monitoring links)
- Individual volcano pages (alert levels, recent activity)
- Program pages (highlighted resources, sections)

### Data Extraction
- **Park Geology**: Title, description, geologic history, sections with content, media galleries, related links
- **Volcano Observatories**: Monitored volcanoes list, alert statuses, threat levels, recent updates
- **Volcano Pages**: Current status, alert level, monitoring data links, recent eruption information
- **Programs**: Organizational descriptions, highlighted resources, section breakdowns

## Usage Examples

### Scrape a Specific Page

```json
{
  "function": "scrape",
  "url": "https://www.usgs.gov/geology-and-ecology-of-national-parks/geology-congaree-national-park"
}
```

Returns structured data with title, description, geologic history, sections, and media.

### Get Park Geology by Name

```json
{
  "function": "get_park_geology",
  "park_name": "Congaree"
}
```

Automatically constructs the URL and extracts geological information.

### Get Volcano Information

```json
{
  "function": "get_volcano_info",
  "volcano_name": "Kilauea"
}
```

Returns current status, alert level, monitoring links, and recent updates.

### Search USGS Content

```json
{
  "function": "search",
  "query": "landslides California",
  "limit": 10
}
```

Searches USGS for relevant pages and returns titles, URLs, and descriptions.

## Output Structure

### Park Geology Response

```json
{
  "success": true,
  "url": "https://www.usgs.gov/...",
  "page_type": "park_geology",
  "data": {
    "type": "park_geology",
    "title": "Geology of Congaree National Park",
    "description": "Congaree National Park is located in central South Carolina...",
    "geologic_history": [
      "In the Triassic, about 175 million years ago...",
      "During the Cretaceous..."
    ],
    "sections": {
      "Geologic Features": "Description of features...",
      "Hydrology": "Description of hydrology..."
    },
    "media": [
      {
        "src": "https://www.usgs.gov/...",
        "alt": "Map of Congaree National Park",
        "caption": "Various streams flow across the floodplain..."
      }
    ],
    "related_links": [
      {"text": "Related Park", "url": "https://..."}
    ]
  }
}
```

### Volcano Observatory Response

```json
{
  "success": true,
  "url": "https://www.usgs.gov/observatories/hvo",
  "page_type": "volcano_observatory",
  "data": {
    "type": "volcano_observatory",
    "title": "Hawaiian Volcano Observatory",
    "description": "HVO monitors earthquakes and active volcanoes in Hawaii...",
    "volcanoes": [
      {"name": "Kīlauea", "url": "https://www.usgs.gov/volcanoes/kilauea"},
      {"name": "Mauna Loa", "url": "https://www.usgs.gov/volcanoes/mauna-loa"}
    ],
    "alerts": ["Very High Threat Potential - Kīlauea"],
    "recent_updates": ["Hawaiian Volcano Observatory Message..."],
    "quick_links": [
      {"text": "Monitoring", "url": "https://..."},
      {"text": "Webcams", "url": "https://..."}
    ]
  }
}
```

### Volcano Page Response

```json
{
  "success": true,
  "url": "https://www.usgs.gov/volcanoes/kilauea",
  "page_type": "volcano",
  "data": {
    "type": "volcano",
    "title": "Kīlauea",
    "description": "Kīlauea is the youngest and most active volcano...",
    "status": "yellow ADVISORY, 2024-01-15...",
    "alert_level": "ADVISORY",
    "monitoring_data": [
      {"type": "Webcams", "url": "https://..."},
      {"type": "Deformation Data", "url": "https://..."}
    ],
    "recent_updates": ["Latest eruption update..."]
  }
}
```

## Notes

- Pages are fetched using browser automation to bypass AWS WAF/CAPTCHA protection
- Extraction may take 5-10 seconds per page
- Some pages may still be blocked if protection is triggered multiple times
- Retry logic is built in for transient failures
- Media URLs are converted to absolute URLs when necessary
- Related links are filtered to relevant internal USGS content

## Common Park Names

- Yellowstone
- Grand Canyon
- Congaree
- Yosemite
- Zion
- Bryce Canyon
- Grand Teton
- Arches
- Canyonlands
- Great Smoky Mountains

## Active Volcanoes (HVO)

- Kīlauea (Very High Threat)
- Mauna Loa (Very High Threat)
- Hualālai (High Threat)
- Haleakalā (Moderate Threat)
- Mauna Kea (Moderate Threat)
- Kama'ehuakanaloa/Lō'ihi (Not Ranked)

## Error Handling

The skill returns structured error responses rather than raising exceptions:

```json
{
  "success": false,
  "error": "Page blocked or unavailable",
  "url": "https://..."
}
```

Common errors:
- Page blocked by WAF/CAPTCHA
- Timeout loading page
- Invalid URL format
- Missing required parameters