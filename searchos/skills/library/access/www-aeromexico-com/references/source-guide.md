# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Aeromexico Baggage Information Access Skill

## Overview

This skill retrieves carry-on baggage policy information from Aeromexico's official website (www.aeromexico.com). It handles the site's Single Page Application (SPA) architecture and provides robust content extraction even when the site experiences maintenance periods.

## Target URLs

- **English**: `https://www.aeromexico.com/en-us/travel-information/baggage/carry-on-baggage`
- **Spanish**: `https://www.aeromexico.com/es-us/informacion-de-vuelos/equipaje/equipaje-de-mano`

## Available Functions

### 1. `get_carry_on_english`

Retrieves carry-on baggage information in English.

**Returns:**
- Page title and headings
- Policy paragraphs and list items
- Weight and size limit specifications
- Full text content (up to 5000 characters)

### 2. `get_carry_on_spanish`

Retrieves carry-on baggage information in Spanish (equipaje de mano).

**Returns:**
- Same structure as English version, but in Spanish

### 3. `get_by_url`

Fetches baggage information from a custom Aeromexico URL.

**Parameters:**
- `url` (required): Target URL from aeromexico.com domain
- `locale` (optional): Locale for content extraction (default: en-US)

**Use Cases:**
- Checked baggage policies
- Special baggage rules
- Other travel information pages

### 4. `check_status`

Checks if the Aeromexico website is currently accessible or under maintenance.

**Returns:**
- `site_accessible`: Boolean indicating if site is operational
- `is_maintenance`: Boolean indicating if maintenance page is shown
- `page_title`: Current page title

## Technical Notes

### SPA Handling

Aeromexico's website is a heavy Single Page Application that requires:
- JavaScript rendering via Playwright
- Extended wait times for content hydration
- Bot detection bypass measures

### Maintenance Detection

The skill automatically detects when the site shows maintenance pages and returns appropriate status messages instead of failing.

### Content Extraction

The skill extracts:
- **Structured content**: Headings, paragraphs, lists, tables
- **Baggage-specific data**: Weight limits (kg/lbs), size dimensions
- **Full text**: Complete page content for analysis

## Response Structure

```json
{
  "status": "success|maintenance|error",
  "url": "https://...",
  "page_title": "Carry-on Baggage | Aeromexico",
  "headings": ["Carry-on Baggage", "Weight Limits", ...],
  "paragraphs": ["All passengers may bring...", ...],
  "lists": ["1 personal item", "1 carry-on bag", ...],
  "tables": [[...], ...],
  "baggage_specific": {
    "weight_limits": ["10 kg", "22 lbs"],
    "size_limits": ["55 x 35 x 25 cm"]
  },
  "full_text": "Complete page text..."
}
```

## Error Handling

- **Maintenance mode**: Returns status `maintenance` with explanatory message
- **Network errors**: Returns status `error` with error details
- **Invalid URLs**: Returns error for non-Aeromexico domains

## Known Limitations

1. **Site Availability**: Aeromexico's website frequently enters maintenance mode, during which content cannot be retrieved.

2. **Dynamic Content**: Some information may be loaded dynamically and require additional wait time.

3. **Rate Limiting**: Excessive requests may trigger anti-bot measures.

## Example Usage

```json
// Get English carry-on info
{"function": "get_carry_on_english"}

// Get Spanish carry-on info
{"function": "get_carry_on_spanish"}

// Check site status
{"function": "check_status"}

// Get checked baggage info
{
  "function": "get_by_url",
  "url": "https://www.aeromexico.com/en-us/travel-information/baggage/checked-baggage"
}
```

## Troubleshooting

If you receive maintenance status:
1. Use `check_status` to verify site availability
2. Wait and retry later
3. The site typically recovers within hours

If content extraction fails:
1. The site may have changed structure
2. Try a different locale
3. Use `check_status` to verify site is operational
