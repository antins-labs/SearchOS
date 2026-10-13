# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ISO 3166 Country Code Data Skill

This skill retrieves ISO 3166-1 country code information from the ISO Online Browsing Platform (OBP) at www.iso.org.

## Features

- Retrieves comprehensive country code data including:
  - Alpha-2 code (2-letter code, e.g., US, DE, NL)
  - Alpha-3 code (3-letter code, e.g., USA, DEU, NLD)
  - Numeric code (3-digit code, e.g., 840, 276, 528)
  - Short name (official English name)
  - Full name
  - Independence status
  - Official status
  - Administrative languages
  - Subdivision information (states, provinces, etc.)

## Usage

### Get Country Information

Retrieve ISO 3166-1 data for a specific country:

```json
{
  "function": "get_country",
  "country_code": "US"
}
```

Example response:
```json
{
  "success": true,
  "country_code": "US",
  "alpha_2_code": "US",
  "alpha_3_code": "USA",
  "numeric_code": "840",
  "short_name": "UNITED STATES OF AMERICA",
  "short_name_lower": "United States of America (the)",
  "full_name": "the United States of America",
  "independent": "Yes",
  "status": "Officially assigned",
  "administrative_language_alpha_2": "en",
  "administrative_language_alpha_3": "eng",
  "local_short_name": "United States of America (the)",
  "subdivisions": [
    {"category": "state", "code": "US-AL", "name": "Alabama"},
    {"category": "state", "code": "US-AK", "name": "Alaska"},
    ...
  ],
  "subdivision_count": 57,
  "source": "ISO 3166-1",
  "source_url": "https://www.iso.org/obp/ui/#iso:code:3166:US"
}
```

## Supported Country Codes

All valid ISO 3166-1 alpha-2 country codes are supported, including:
- **US** - United States of America
- **DE** - Germany
- **NL** - Netherlands (Kingdom of the)
- **FR** - France
- **GB** - United Kingdom
- **JP** - Japan
- **CN** - China
- **AU** - Australia
- **CA** - Canada
- And all other officially assigned country codes

## Technical Notes

This skill uses browser automation (Playwright) to access the ISO OBP because:
1. The site uses Cloudflare security verification
2. The OBP is a Vaadin JavaScript application that loads data asynchronously
3. Direct HTTP requests cannot retrieve the country code data

The skill implements:
- Retry logic for reliability
- Intelligent waiting for content to load
- Robust parsing of the rendered page content

## Error Handling

The skill returns structured error responses for:
- Invalid country code format (must be 2 letters)
- Country code not found in ISO 3166-1
- Page loading failures

Example error response:
```json
{
  "success": false,
  "country_code": "XX",
  "error": "Country code \"XX\" not found in ISO 3166-1."
}
```
