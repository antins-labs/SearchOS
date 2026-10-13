# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Smithsonian Global Volcanism Program Access Skill

This skill retrieves volcano data from the Smithsonian Institution's Global Volcanism Program database at volcano.si.edu.

## Available Functions

### 1. get_country_volcanos
Retrieves a list of volcanoes for a specified country.

**Parameters:**
- `country` (required): Country name (e.g., "Panama", "Taiwan", "Japan", "Indonesia")

**Example:**
```json
{
  "function": "get_country_volcanos",
  "country": "Panama"
}
```

### 2. get_volcano_details
Retrieves detailed information about a specific volcano.

**Parameters:**
- `volcano_number` (required): The unique volcano identifier (e.g., "344100")

**Example:**
```json
{
  "function": "get_volcano_details",
  "volcano_number": "344100"
}
```

### 3. get_ring_of_fire
Retrieves information about the Pacific Ring of Fire from the FAQ section.

**Example:**
```json
{
  "function": "get_ring_of_fire"
}
```

### 4. check_access
Checks whether the site is currently accessible or blocked by Cloudflare protection.

**Example:**
```json
{
  "function": "check_access"
}
```

## Important Notes

### Cloudflare Protection
This site uses Cloudflare managed challenge protection that specifically targets automated browsers. The skill implements several anti-detection measures, but access may still be blocked. When blocked, the skill will return:
```json
{
  "success": false,
  "error": "cloudflare_blocked",
  "message": "Cloudflare challenge could not be resolved..."
}
```

### Data Available
The Smithsonian Global Volcanism Program database contains:
- Comprehensive volcano listings by country
- Individual volcano details including:
  - Geographic coordinates
  - Elevation
  - Rock types
  - Eruption history
  - Tectonic setting
- Holocene volcano information
- Weekly volcanic activity reports

### Rate Limiting
Please be respectful when making multiple requests. The skill implements appropriate delays and timeout handling.

## Response Format

All functions return a consistent response format:

**Success:**
```json
{
  "success": true,
  "country": "Panama",
  "url": "https://volcano.si.edu/volcanolist_countries.cfm?country=Panama",
  "page_title": "Volcanoes of Panama",
  "volcanos": [
    {
      "name": "Barú",
      "volcano_number": "346010",
      "url": "https://volcano.si.edu/volcano.cfm?vnum=346010"
    }
  ],
  "total_count": 1
}
```

**Error:**
```json
{
  "success": false,
  "error": "cloudflare_blocked",
  "message": "Cloudflare challenge could not be resolved",
  "url": "https://volcano.si.edu/..."
}
```

## Troubleshooting

If you consistently receive `cloudflare_blocked` errors:
1. Try again later - Cloudflare restrictions may be temporary
2. Use `check_access` to verify current site status
3. The site may be experiencing high traffic or maintenance

## Source
Data sourced from: Smithsonian Institution Global Volcanism Program
https://volcano.si.edu/
