# GSMArena Phone Specifications Skill

Extract comprehensive phone specifications from GSMArena.com, the world's largest mobile device database.

## Overview

GSMArena hosts detailed specifications for thousands of mobile devices including smartphones, tablets, and wearables. This skill extracts the complete technical specifications organized into categories such as:

- **Network** - 2G, 3G, 4G, 5G bands and technology support
- **Launch** - Announcement date and release status
- **Body** - Dimensions, weight, build materials, SIM type, IP ratings
- **Display** - Type, size, resolution, protection
- **Platform** - OS, chipset, CPU, GPU
- **Memory** - Internal storage, RAM, card slot
- **Main Camera** - Sensors, features, video capabilities
- **Selfie Camera** - Front camera specifications
- **Sound** - Loudspeaker, 3.5mm jack, audio features
- **Comms** - Wi-Fi, Bluetooth, USB, NFC, positioning
- **Features** - Sensors, special features
- **Battery** - Capacity, charging, endurance
- **Misc** - Colors, models, SAR values, price

## Functions

### `get_phone_specs`

Get full specifications for a phone from GSMArena.

**Parameters:**
- `url` (string, optional): Full URL to the GSMArena phone page
  - Example: `https://www.gsmarena.com/samsung_galaxy_s20-10081.php`
- `phone_id` (string, optional): Phone ID from GSMArena URL
  - Example: `samsung_galaxy_s20-10081`

One of `url` or `phone_id` is required.

**Example:**
```python
result = await execute({
    "function": "get_phone_specs",
    "url": "https://www.gsmarena.com/samsung_galaxy_s20-10081.php"
})
```

**Response Structure:**
```json
{
  "success": true,
  "url": "https://www.gsmarena.com/samsung_galaxy_s20-10081.php",
  "phone_name": "Samsung Galaxy S20",
  "phone_image": "https://fdn2.gsmarena.com/vv/bigpic/samsung-galaxy-s20-.jpg",
  "quickspecs": {},
  "specs_raw": [
    {
      "name": "Network",
      "specs": [
        {"name": "Technology", "value": "GSM / CDMA / HSPA / EVDO / LTE"},
        {"name": "2G bands", "value": "GSM 850 / 900 / 1800 / 1900"}
      ]
    }
  ],
  "specs_structured": {
    "network": {
      "display_name": "Network",
      "specs": {
        "technology": {"display_name": "Technology", "value": "GSM / CDMA / HSPA / EVDO / LTE"}
      }
    }
  },
  "total_categories": 14,
  "total_specs": 53
}
```

### `parse_specs_structure`

Parse raw specifications into a structured format.

**Parameters:**
- `specs_data` (object): Raw specs data from `get_phone_specs`

**Example:**
```python
result = await execute({
    "function": "parse_specs_structure",
    "specs_data": raw_specs
})
```

## Usage Examples

### Get specs by URL
```python
result = await execute({
    "function": "get_phone_specs",
    "url": "https://www.gsmarena.com/samsung_galaxy_s20-10081.php"
})

if result["success"]:
    print(f"Phone: {result['phone_name']}")
    for category in result['specs_raw']:
        print(f"\n{category['name']}:")
        for spec in category['specs']:
            print(f"  {spec['name']}: {spec['value']}")
```

### Get specs by phone ID
```python
result = await execute({
    "function": "get_phone_specs",
    "phone_id": "samsung_galaxy_note5_(usa)-7504"
})
```

### Access structured specs
```python
result = await execute({
    "function": "get_phone_specs",
    "url": "https://www.gsmarena.com/samsung_galaxy_s20-10081.php"
})

if result["success"]:
    structured = result['specs_structured']
    
    # Access specific categories
    display = structured.get('display', {}).get('specs', {})
    print(f"Size: {display.get('size', {}).get('value')}")
    print(f"Resolution: {display.get('resolution', {}).get('value')}")
    
    battery = structured.get('battery', {}).get('specs', {})
    print(f"Capacity: {battery.get('type', {}).get('value')}")
```

## Error Handling

The skill returns structured errors with `success: false`:

```json
{
  "success": false,
  "error": "Phone page not found",
  "error_type": "extraction_failed",
  "url": "..."
}
```

**Error types:**
- `missing_parameter` - Required parameter not provided
- `invalid_phone_id` - Phone ID format is invalid
- `extraction_failed` - Could not extract specs from page
- `timeout` - Request timed out
- `request_failed` - Network or server error

## Notes

- GSMArena uses Cloudflare Turnstile protection, which is handled automatically
- Rate limiting: 10 requests/minute, 100 requests/hour
- Typical response includes 10-15 categories with 3-10 specs each
- Some specs may include links to related phones or details

## URL Pattern

GSMArena phone URLs follow this pattern:
```
https://www.gsmarena.com/{brand}_{model}-{id}.php
```

Examples:
- `samsung_galaxy_s20-10081.php`
- `apple_iphone_15_pro_max-12965.php`
- `samsung_galaxy_note5_(usa)-7504.php`