# Ctrip Attraction Data Access Skill

Access attraction and sight data from Ctrip (携程), one of China's largest travel platforms.

## Overview

This skill fetches structured information about tourist attractions/sights from Ctrip's mobile API. It provides comprehensive data including:

- **Basic Information**: Attraction name, POI ID, district/location
- **Pricing**: Ticket prices, free/paid status, price type descriptions
- **Descriptions**: Attraction introductions and ticket descriptions
- **Travel Tips**: Talent notes with user-generated reviews and guides

## Supported Functions

### `get_sight_info`

Fetches complete information about a sight/attraction.

**Parameters:**
- `sight_id` (required): The attraction's business ID or full URL
- `timeout` (optional): Request timeout in seconds (default: 15)

**Returns:**
```json
{
  "success": true,
  "error": null,
  "data": {
    "sight_id": 109784,
    "poi_id": 91339,
    "name": "西沙明珠湖景区",
    "poi_type": 3,
    "district_id": 2,
    "price": {
      "amount": 0.0,
      "currency": "CNY",
      "type": "1",
      "type_desc": "免费预约"
    },
    "ticket_description": "免费预约",
    "introduction": "【景区简介】\n西沙明珠湖景区位于...",
    "talent_notes": {
      "total_count": 306,
      "description": "300+篇达人笔记等你发现",
      "items": [...]
    }
  }
}
```

## Usage Examples

### Example 1: Get attraction info by ID

```json
{
  "function": "get_sight_info",
  "sight_id": "109784"
}
```

### Example 2: Get attraction info by URL

```json
{
  "function": "get_sight_info",
  "sight_id": "https://gs.ctrip.com/html5/you/sight/shanghai2/109784.html"
}
```

### Example 3: With custom timeout

```json
{
  "function": "get_sight_info",
  "sight_id": "14407",
  "timeout": 30
}
```

## Data Sources

The skill uses Ctrip's internal REST API:
- Endpoint: `https://m.ctrip.com/restapi/soa2/20036/json/getSightExtendInfo`
- Method: POST
- No authentication required for basic information

## Notes

- **Rate Limiting**: The API may have rate limits; avoid making too many requests in quick succession
- **Free vs Paid**: Price type "1" typically means free reservation required, "2" means paid tickets
- **Language**: All content is in Chinese (Simplified)
- **Talent Notes**: Limited to top 5 notes in the response for brevity
- **Place Pages**: URLs matching `/you/place/` are destination guides, not individual attractions and may not be supported

## Error Handling

The skill returns structured errors without raising exceptions:

```json
{
  "success": false,
  "error": "Sight not found or invalid ID",
  "data": null
}
```

Common error cases:
- Invalid sight ID
- Network timeouts
- API unavailable

## Supported URL Patterns

The skill can extract sight IDs from various Ctrip URL formats:
- `https://gs.ctrip.com/html5/you/sight/{city}/{id}.html`
- `https://m.ctrip.com/webapp/you/sight/{city}/{id}.html`
- Direct numeric IDs