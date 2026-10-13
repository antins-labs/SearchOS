# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Hong Kong Railway Encyclopedia (hkrailen.fandom.com) Access Skill

This skill retrieves structured railway line information from the Hong Kong Railway Encyclopedia Fandom wiki, including infobox data, station lists, and page content.

## Overview

The skill uses the Fandom MediaWiki API to bypass Cloudflare protection and reliably access wiki content. It extracts structured data from portable infoboxes and station tables.

## Available Functions

### `get_page_info`
Retrieve comprehensive information about a wiki page.

**Parameters:**
- `page_title` (required): Wiki page title in URL format (e.g., "Tseung_Kwan_O_Line")
- `include_sections` (optional, default: true): Whether to include section list

**Returns:**
- Page title and display title
- Infobox data (line code, termini, route length, number of stations, opened date, travel time, operator, depot, train types, gauge, power supply, signaling, max speed, etc.)
- Station list with names, codes, and platform info
- Page description (first meaningful paragraph)
- Section list (if requested)

**Example:**
```json
{
  "function": "get_page_info",
  "page_title": "Tseung_Kwan_O_Line"
}
```

### `get_infobox`
Retrieve just the infobox data from a wiki page.

**Parameters:**
- `page_title` (required): Wiki page title

**Returns:**
- Title
- Structured infobox data with field names and values

**Example:**
```json
{
  "function": "get_infobox",
  "page_title": "Island_Line"
}
```

### `get_station_list`
Retrieve the station list from a railway line page.

**Parameters:**
- `page_title` (required): Wiki page title

**Returns:**
- List of stations with names, codes, and platform information

**Example:**
```json
{
  "function": "get_station_list",
  "page_title": "Tsuen_Wan_Line"
}
```

### `search_pages`
Search for wiki pages matching a query.

**Parameters:**
- `query` (required): Search query
- `limit` (optional, default: 10): Maximum number of results

**Returns:**
- List of matching pages with titles, page IDs, snippets, and timestamps

**Example:**
```json
{
  "function": "search_pages",
  "query": "Line",
  "limit": 5
}
```

### `get_section_content`
Retrieve content of a specific section from a page.

**Parameters:**
- `page_title` (required): Wiki page title
- `section` (required): Section number or name

**Returns:**
- Section title
- Text content
- Raw HTML (if needed)

**Example:**
```json
{
  "function": "get_section_content",
  "page_title": "Tseung_Kwan_O_Line",
  "section": "1"
}
```

## Data Extracted from Infobox

For railway line pages, the infobox typically includes:
- **Line code**: Abbreviation (e.g., TKL, ISL, TWL)
- **Termini**: Start and end stations
- **Route Length**: Total length in kilometers
- **Number Of Stations**: Total station count
- **Opened Date**: Opening dates for different sections
- **Travel Time**: Journey duration
- **Current Operator**: Operating company
- **Currently Dispatching Depot**: Maintenance depot
- **Main Train**: Train types used
- **Gauge**: Track gauge
- **Electrochemical Mode**: Power supply system
- **Signal System**: Signaling technology
- **Max speed Limit**: Maximum operating speed

## Common Page Titles

Some commonly queried railway lines:
- `Tseung_Kwan_O_Line` - 将军澳线
- `Island_Line` - 港岛线
- `Tsuen_Wan_Line` - 荃湾线
- `Kwun_Tong_Line` - 观塘线
- `East_Rail_Line` - 东铁线
- `West_Rail_Line` - 西铁线
- `Tuen_Ma_Line` - 屯马线
- `South_Island_Line` - 南港岛线
- `Disneyland_Resort_Line` - 迪士尼线
- `Airport_Express` - 机场快线

## Error Handling

The skill returns structured error responses:
```json
{
  "success": false,
  "error": "Error message describing the issue",
  "page": "Page_Title"
}
```

Common errors:
- Missing required parameter
- Page not found
- API error from Fandom

## Technical Notes

- Uses MediaWiki API (`api.php`) to bypass Cloudflare protection
- Parses HTML with BeautifulSoup for structured data extraction
- Handles both English and Chinese content in station names
- Extracts portable infobox data (Fandom's infobox format)
- Parses wikitable station lists with automatic column detection
