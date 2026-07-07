# Autohome Vehicle Configuration Extractor

Extract comprehensive vehicle specifications and configuration data from Autohome (汽车之家) - China's leading automotive portal.

## Overview

This skill extracts detailed vehicle configuration data from `car.autohome.com.cn`, including:
- Basic parameters (基本参数): pricing, dimensions, powertrain specs
- Body specifications (车身): length, width, height, wheelbase, weight
- Electric motor details (电动机): motor type, power, torque
- Battery/charging info (电池/充电): battery type, capacity, charging time
- Transmission (变速箱): gearbox specifications
- Chassis/steering (底盘转向): suspension, steering system
- Wheels/brakes (车轮制动): tire specs, brake types
- Safety features (被动安全, 主动安全): airbags, ABS, stability control
- Driving features (驾驶操控, 驾驶硬件, 驾驶功能): driving modes, ADAS

## Functions

### 1. `get_config` - Get Single Series Configuration

Retrieve complete configuration data for a vehicle series.

**Parameters:**
- `url` (string, optional): Full URL of the configuration page
- `series_id` (string, optional): Series ID (will construct URL automatically)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)

**Example:**
```python
# Using URL
result = await execute({
    "function": "get_config",
    "url": "https://car.autohome.com.cn/config/series/7806.html"
})

# Using series ID
result = await execute({
    "function": "get_config",
    "series_id": "7806"
})
```

**Response Structure:**
```json
{
  "success": true,
  "url": "https://car.autohome.com.cn/config/series/7806.html",
  "series_id": "7806",
  "model_count": 11,
  "models": [
    {"spec_id": "77986", "name": "星愿 2026款 310km 向往版"},
    ...
  ],
  "spec_ids": ["77986", "77987", ...],
  "parameters": [
    {
      "name": "基本参数",
      "items": [
        {
          "name": "厂商指导价(万元)",
          "id": -1,
          "values": {
            "77986": {"value": "6.48", ...},
            ...
          }
        }
      ]
    }
  ],
  "configurations": [...],
  "summary": {
    "parameter_categories": 7,
    "total_parameters": 76,
    "configuration_categories": 15,
    "total_configurations": 150
  }
}
```

### 2. `get_multiple` - Get Multiple Series Configurations

Batch fetch configurations for multiple vehicle series.

**Parameters:**
- `series_ids` (array of strings): List of series IDs
- `timeout` (integer, optional): Request timeout in seconds

**Example:**
```python
result = await execute({
    "function": "get_multiple",
    "series_ids": ["7806", "5769", "6762"]
})
```

### 3. `compare` - Compare Variants Within a Series

Generate a comparison table for different variants (specs) within a single series.

**Parameters:**
- `url` or `series_id`: Identify the vehicle series
- `spec_ids` (array of strings, optional): Specific variants to compare
- `timeout` (integer, optional): Request timeout in seconds

**Example:**
```python
# Compare all variants
result = await execute({
    "function": "compare",
    "series_id": "7806"
})

# Compare specific variants
result = await execute({
    "function": "compare",
    "series_id": "7806",
    "spec_ids": ["77986", "77987", "77984"]
})
```

**Response Structure:**
```json
{
  "models": [
    {"spec_id": "77986", "name": "星愿 2026款 310km 向往版"},
    {"spec_id": "77987", "name": "星愿 2026款 310km 乘悦版"}
  ],
  "parameters": [
    {
      "category": "基本参数",
      "parameter": "厂商指导价(万元)",
      "values": {
        "77986": "6.48",
        "77987": "7.18"
      }
    }
  ]
}
```

## Data Sources

The skill extracts data from:
- Embedded `var config` JSON: Vehicle parameters and specifications
- Embedded `var option` JSON: Configuration options and features
- Page HTML: `https://car.autohome.com.cn/config/series/{series_id}.html`

## Data Processing

- HTML tags and entities are automatically removed from text values
- Non-breaking spaces (`&nbsp;`) are converted to regular spaces
- Values are structured by spec_id for easy cross-referencing
- Categories are organized hierarchically for intuitive navigation

## Use Cases

1. **Vehicle Research**: Extract complete specs for vehicle comparison
2. **Price Analysis**: Gather pricing data across multiple variants
3. **Feature Comparison**: Compare safety, comfort, and technology features
4. **Market Intelligence**: Track specifications across competing models
5. **Database Building**: Create structured vehicle specification databases

## Example Vehicle Series

- **7806**: Geely Xingyuan (吉利星愿) - Electric hatchback
- **5769**: Tesla Model Y - Electric SUV
- **6762**: BYD Seagull (比亚迪海鸥) - Electric mini car

## Technical Notes

- No API key required
- Data is extracted from embedded JavaScript variables in HTML
- Supports both electric and traditional vehicles
- All text values are cleaned of HTML markup
- Rate limit: 2 requests/second, 60 requests/minute

## Error Handling

Returns structured error responses:
```json
{
  "error": "config_not_found",
  "message": "Configuration data not found in page"
}
```

Common errors:
- `missing_parameter`: Required parameter not provided
- `config_not_found`: Vehicle series page doesn't contain expected data
- `network_error`: Failed to fetch the page
- `config_parse_error`: Failed to parse the configuration JSON