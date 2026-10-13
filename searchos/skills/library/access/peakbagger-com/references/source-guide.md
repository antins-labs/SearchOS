# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Peakbagger.com Access Skill

Access mountain range and peak data from Peakbagger.com, a comprehensive database of mountain peaks, ranges, and climbing information.

## Overview

This skill retrieves structured data from Peakbagger.com's range pages, which contain:
- Range metadata (type, area, extent, coordinates)
- Top 10 highest peaks with elevations
- Child range high points
- Geographic hierarchy (parent, children, siblings)
- Country and state/province coverage

## Important Limitations

**Cloudflare Protection**: Peakbagger.com uses Cloudflare bot protection that blocks access to:
- Individual peak pages (`peak.aspx?pid=XXX`)
- List pages (`List.aspx?lid=XXX`)

However, **range pages are accessible** and contain comprehensive peak data including the top 10 highest peaks for each range.

## Functions

### get_range

Get detailed information about a specific mountain range.

**Parameters:**
- `rid` (string): Range ID number (e.g., "100" for Brooks Range)
- `url` (string): Full range page URL (alternative to rid)

**Example:**
```json
{
  "function": "get_range",
  "rid": "100"
}
```

**Returns:**
- Range name and type
- Highest point with peak ID
- Countries and states/provinces
- Area and extent
- Center coordinates
- Top 10 highest peaks with elevations
- Child range high points
- Hierarchy (parent, children, siblings)

### search_ranges

Explore the range hierarchy to discover mountain ranges.

**Parameters:**
- `start_rid` (string, optional): Starting range ID (default: "1" for North America)
- `max_depth` (integer, optional): Hierarchy depth limit (default: 1)

**Example:**
```json
{
  "function": "search_ranges",
  "start_rid": "10"
}
```

### get_peak_from_range

Find peak information within a range page.

**Parameters:**
- `rid` (string, required): Range ID where the peak is located
- `peak_name` (string, optional): Peak name (partial match)
- `peak_id` (string, optional): Peak ID for exact match

**Example:**
```json
{
  "function": "get_peak_from_range",
  "rid": "100",
  "peak_name": "Isto"
}
```

## Range ID Reference

Some notable range IDs:
- `1` - North America (continent)
- `10` - Alaska-Yukon Ranges
- `22` - Guiana Highlands
- `100` - Brooks Range
- `200` - Coastal Venezuela
- `500` - Rocky Mountains (Canadian)

You can discover more ranges by exploring the hierarchy returned from `get_range` or `search_ranges`.

## Data Fields

### Range Information
- `range_name`: Name of the mountain range
- `range_type`: Type (e.g., "Mountain range", "Highland or plateau", "Continent")
- `highest_point`: Object with peak name, ID, and elevation
- `countries`: Countries the range spans
- `area`: Total area in sq km and sq mi
- `extent`: North-South and East-West dimensions
- `center_coordinates`: Lat/Long of range center

### Peak Information
- `rank`: Ranking within the range
- `name`: Peak name
- `peak_id`: Peakbagger database ID
- `elevation_ft`: Elevation in feet
- `elevation_m`: Elevation in meters
- `sub_range`: Sub-range the peak belongs to

### Hierarchy
- `parent`: Parent range (e.g., continent → mountain system)
- `children`: Sub-ranges within this range
- `siblings`: Other ranges at the same level

## Use Cases

1. **Mountain Research**: Get comprehensive data about a mountain range
2. **Peak Discovery**: Find the highest peaks in a region
3. **Geographic Exploration**: Navigate the mountain range hierarchy
4. **Trip Planning**: Identify notable peaks in an area

## Technical Notes

- Uses Playwright browser automation to access the site
- Implements rate limiting to avoid triggering Cloudflare
- Parses HTML tables for structured data extraction
- Returns data in normalized JSON format
