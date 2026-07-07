# CMSE (China Manned Space Engineering) Access Skill

Access skill for extracting structured data from China's official space program website at www.cmse.gov.cn.

## Overview

This skill extracts mission profiles, timelines, crew information, and news from the China Manned Space Engineering (CMSE) website. It provides access to information about:

- **Shenzhou (神舟)** - Crewed spacecraft missions (SZ-1 through SZ-23+)
- **Tiangong (天宫)** - Space station and laboratory modules
- **Tianzhou (天舟)** - Cargo spacecraft missions
- **Long March (长征)** - Launch vehicle missions

## Website Structure

The CMSE website follows a predictable structure:

- Mission pages: `https://www.cmse.gov.cn/fxrw/{mission_id}/`
  - Examples: `/fxrw/SZ19/` (Shenzhou-19), `/fxrw/tz9h/` (Tianzhou-9)
  
- Timeline articles: Various paths under `/fxrw/szwh/` and `/xwzx/`
  
- Mission lists: `https://www.cmse.gov.cn/col/col9/index.html` (flight missions)

## Functions

### get_mission_details

Retrieve detailed information about a specific mission.

**Parameters:**
- `mission_url` (optional): Full URL of the mission page
- `mission_id` (optional): Mission ID like 'SZ19', 'SZ21', 'tz9h', etc.

**Example:**
```json
{
  "function": "get_mission_details",
  "mission_id": "SZ19"
}
```

**Returns:**
- Mission title, name, launch time, location
- Crew members (when available)
- Related news items with titles and URLs
- Mission description

### get_timeline

Extract chronological timeline events from timeline article pages.

**Parameters:**
- `article_url` (required): URL of the timeline article

**Example:**
```json
{
  "function": "get_timeline",
  "article_url": "https://www.cmse.gov.cn/fxrw/szwh/jchg_193/200809/t20080917_23556.html"
}
```

**Returns:**
- Parsed timeline events with timestamps and descriptions
- Each event includes parsed date/time components
- Full article content

### list_missions

List available missions from the website.

**Parameters:**
- `page_type` (optional): 'current' or 'history' (default: 'current')

**Example:**
```json
{
  "function": "list_missions",
  "page_type": "current"
}
```

**Returns:**
- Array of missions with names, URLs, and basic info
- Total count of available missions

### get_article

Retrieve full content from any CMSE article page.

**Parameters:**
- `article_url` (required): URL of the article

**Example:**
```json
{
  "function": "get_article",
  "article_url": "https://www.cmse.gov.cn/xwzx/202507/t20250709_56720.html"
}
```

**Returns:**
- Article title and full text content
- Publication date
- Timeline events (if present in the article)

### search

Search for missions or content by keyword.

**Parameters:**
- `keyword` (required): Search term (Chinese or English)

**Example:**
```json
{
  "function": "search",
  "keyword": "神舟十九"
}
```

**Returns:**
- Matching missions and articles
- Titles, URLs, and snippets

## Chinese Date Format Handling

The skill handles Chinese date/time formats commonly used on the site:

- `2003年10月15日5时20分` → October 15, 2003 at 05:20
- `2024年4月25日` → April 25, 2024

Parsed dates include year, month, day, hour (if present), and minute (if present).

## Common Mission IDs

| Prefix | Type | Examples |
|--------|------|----------|
| SZ | Shenzhou (crewed) | SZ19, SZ20, SZ21, SZ23 |
| TG | Tiangong (station) | TG1, TG2 |
| TZ | Tianzhou (cargo) | tz9h, ttz10h |
| CZ | Long March (rocket) | cz7 |

## Technical Notes

- Uses aiohttp for direct HTTP requests (no browser automation needed)
- BeautifulSoup for HTML parsing
- Handles Chinese character encoding correctly
- Rate-limited to 2 requests/second to respect the server

## Error Handling

All functions return structured error responses:

```json
{
  "success": false,
  "error": "Description of error",
  "error_type": "parameter_error|fetch_error|execution_error"
}
```

## Data Quality Notes

- Mission names and details are scraped from the official website
- Some historical missions may have limited information
- Crew information is extracted when available in the page content
- News links are deduplicated by URL

## Use Cases

1. **Mission Research**: Get detailed information about specific Chinese space missions
2. **Timeline Analysis**: Extract chronological events for mission planning research
3. **News Tracking**: Follow updates about active missions
4. **Historical Archives**: Access information about completed missions
5. **Crew Information**: Find astronauts for specific missions

## Example: Complete Workflow

```json
// 1. List available missions
{"function": "list_missions", "page_type": "current"}

// 2. Get details for a specific mission
{"function": "get_mission_details", "mission_id": "SZ19"}

// 3. Search for related content
{"function": "search", "keyword": "神舟十九号"}

// 4. Get article details
{"function": "get_article", "article_url": "https://www.cmse.gov.cn/xwzx/..."}

// 5. Get timeline if available
{"function": "get_timeline", "article_url": "https://www.cmse.gov.cn/fxrw/szwh/..."}
```