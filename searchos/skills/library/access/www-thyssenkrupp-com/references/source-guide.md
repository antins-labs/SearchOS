# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ThyssenKrupp History Access Skill

This skill fetches structured historical timeline data from the thyssenkrupp.com company history page.

## Overview

The thyssenkrupp history page presents a rich interactive timeline spanning from 1811 to the present day, documenting the history of both the Krupp and Thyssen families and their eventual merger. The page uses an Angular-based frontend that embeds all timeline data in a `TRANSFER_STATE` JavaScript object, making it easily extractable without requiring browser automation.

## Data Source

- **URL**: https://www.thyssenkrupp.com/en/company/history
- **Method**: HTTP GET with embedded JSON extraction
- **Data Format**: JSON embedded in page HTML as `window['TRANSFER_STATE']`

## Available Functions

### get_history_timeline

Fetches the complete historical timeline with all events from 1811 to present.

**Returns**:
- `page_title`: Page title
- `total_events`: Number of historical events
- `events`: Array of historical events, each containing:
  - `date`: Year or date range (e.g., "1811", "1892 - 1917")
  - `headline`: Event headline (e.g., "Krupp", "Thyssen", or era names like "Beginnings")
  - `is_divider`: Boolean indicating if this is an era marker
  - `image`: Image URL for the event (if available)
  - `link`: Link to detailed page (if available)
  - `dom`: HTML snippet with additional content
- `eras`: Array of historical eras with their year ranges

**Example Response**:
```json
{
  "success": true,
  "data": {
    "page_title": "History",
    "total_events": 76,
    "events": [
      {
        "date": "1811 - 1891",
        "headline": "Beginnings",
        "is_divider": true
      },
      {
        "date": "1811",
        "headline": "Krupp",
        "is_divider": false,
        "image": "https://www.thyssenkrupp.com/assets.files/..."
      }
    ],
    "eras": [
      {
        "period": "1811 - 1891",
        "years": ["1811", "1833", "1836", ...]
      }
    ]
  }
}
```

### get_founding_families

Fetches information about the founding family members.

**Returns**:
- `total_members`: Number of family members listed
- `founding_families`: Array of family members, each containing:
  - `name`: Family member name (e.g., "Friedrich Krupp", "Alfred Krupp", "August Thyssen")
  - `description`: Brief biography excerpt
  - `link`: URL to detailed biography page
  - `image`: Portrait image URL

### get_page_content

Fetches general content sections from the history page.

**Returns**:
- `page_title`: Page title
- `sections`: Array of content sections including:
  - Big image teasers with headlines, descriptions, and links
  - Standard text blocks
  - Text teaser lists
  - Contact teasers

## Historical Eras Covered

The timeline spans several major historical periods:

1. **1811 - 1891**: Beginnings (Krupp and Thyssen founding)
2. **1892 - 1917**: Wilhelminian period
3. **1918 - 1933**: Weimar Republic
4. **1933 - 1945**: Third Reich
5. **1945 - 1997**: Bonn Republic (post-war reconstruction)
6. **1997 - heute**: Modern era (thyssenkrupp formation)

## Technical Notes

- The page uses client-side rendering with Angular
- All data is embedded in the initial HTML response
- No authentication or cookies required
- Image URLs may be relative paths or dynamic image URLs (dynimg.v1: prefix)
- The skill normalizes all image URLs to absolute HTTPS URLs

## Use Cases

- Researching German industrial history
- Understanding the merger of Krupp and Thyssen
- Accessing historical corporate archives
- Analyzing company evolution over time
- Educational content about industrial heritage
