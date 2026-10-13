# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Travel Weekly Cruise Access Skill

This skill retrieves cruise schedule and itinerary information from Travel Weekly's cruise database at www.travelweekly.com.

## Target Pages

The skill is designed for Travel Weekly cruise record pages with URLs following this pattern:
```
https://www.travelweekly.com/Cruise/{Cruise-Line}/{Ship-Name}/Cruise-p{ID}
```

Example:
- https://www.travelweekly.com/Cruise/Viking-Ocean/Viking-Venus/Cruise-p60587758

## Data Retrieved

When successful, the skill extracts:
- **Cruise ID** - Unique identifier from the URL
- **Cruise Line** - Operator name (e.g., Viking Ocean)
- **Ship Name** - Vessel name (e.g., Viking Venus)
- **Departure Date** - Sailing start date
- **Duration** - Number of nights
- **Itinerary** - List of ports and destinations
- **Starting Price** - Base fare when available
- **Description** - Cruise overview text

## Usage

### Using Full URL
```json
{
  "function": "get_cruise",
  "url": "https://www.travelweekly.com/Cruise/Viking-Ocean/Viking-Venus/Cruise-p60587758"
}
```

### Using Components
```json
{
  "function": "get_cruise",
  "cruise_id": "60587758",
  "cruise_line": "Viking Ocean",
  "ship_name": "Viking Venus"
}
```

## Important Limitations

### Cloudflare Protection

Travel Weekly uses **aggressive Cloudflare bot protection** that blocks automated access. The skill implements multiple strategies to handle this:

1. **Browser automation** with anti-detection measures
2. **Extended wait times** for JavaScript challenge completion
3. **Realistic user agent** strings

However, **success is not guaranteed**. The site may:
- Block requests entirely with a "security verification" page
- Require CAPTCHA completion that cannot be automated
- Return 403 Forbidden responses

### Expected Errors

When blocked, the skill returns:
```json
{
  "success": false,
  "error": "Cloudflare protection blocked access. The site requires JavaScript challenge completion that cannot be automated.",
  "data": null
}
```

## Technical Details

### Implementation

The skill uses Playwright browser automation with:
- Headless Chromium browser
- Anti-fingerprinting scripts
- Extended timeout handling (up to 40 seconds for challenge resolution)

### Fallback Parsing

If the page loads successfully, the skill:
1. Parses HTML with BeautifulSoup
2. Extracts JSON-LD structured data
3. Uses regex patterns to find dates, prices, and port names
4. Falls back to URL structure for cruise line and ship names

## When to Use

This skill is most appropriate when:
- You need cruise schedule data from Travel Weekly
- Direct URL access is required
- Alternative data sources are not available

Consider alternative sources if:
- Consistent automated access is required
- Real-time pricing data is needed
- Bulk data extraction is the goal

## Related Resources

- Travel Weekly Cruise Section: https://www.travelweekly.com/Cruise
- Individual cruise lines may have their own APIs or data feeds
- Consider using official cruise line websites for booking data
