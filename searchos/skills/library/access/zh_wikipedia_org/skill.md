# Chinese Wikipedia Access Skill

Access skill for [Chinese Wikipedia](https://zh.wikipedia.org) that extracts structured data from pages including infoboxes, medal records, and competition tables.

## Overview

This skill provides reliable access to Chinese Wikipedia content, focusing on structured data extraction from biographical and sports pages. It uses the official MediaWiki Action API for consistent data retrieval.

### Key Features

- **Search**: Find Wikipedia pages by keyword or phrase
- **Page Data**: Full structured extraction including infobox, tables, and medal records
- **Extract**: Brief text summaries with configurable length
- **Medal Parsing**: Automatic extraction and classification of medal records
- **Rate Limiting**: Built-in retry logic with exponential backoff

## Functions

### search

Search for Wikipedia pages by keyword or phrase.

**Parameters:**
- `query` (required): Search query string
- `limit` (optional): Maximum results, default 10

**Example:**
```json
{
  "function": "search",
  "query": "乒乓球",
  "limit": 5
}
```

**Returns:**
- List of matching pages with titles, page IDs, snippets, and metadata

---

### get_page

Get comprehensive structured data from a Wikipedia page.

**Parameters:**
- `title` (required): Exact page title
- `include_html` (optional): Parse HTML for structured data, default true

**Example:**
```json
{
  "function": "get_page",
  "title": "马龙 (乒乓球运动员)"
}
```

**Returns:**
- Full page data including:
  - `title`: Page title
  - `extract`: Plain text summary
  - `infobox`: Structured infobox data with:
    - `name`: Entity name
    - `personal_info`: Key-value pairs of personal information
    - `medal_summary`: Medal counts by competition type
  - `tables`: Parsed wikitables with headers and rows
  - `medal_records`: Individual medal entries with classification
  - `sections`: Page section structure

---

### get_extract

Get a brief text summary from a Wikipedia page.

**Parameters:**
- `title` (required): Exact page title
- `sentences` (optional): Number of sentences, default 5

**Example:**
```json
{
  "function": "get_extract",
  "title": "张继科",
  "sentences": 3
}
```

**Returns:**
- Page title and plain text extract

## Data Extraction Details

### Infobox Parsing

The skill extracts structured data from Wikipedia infoboxes including:

- Personal information (birth date, nationality, height, weight, etc.)
- Sports/occupation data (club, ranking, playing style, etc.)
- Medal summaries (Olympic, World Championship, World Cup totals)

### Medal Records

Medal records are extracted and classified by type:
- Gold medals
- Silver medals  
- Bronze medals

Each record includes:
- Year/location of competition
- Event type
- Medal classification

### Tables

Wikitable data is parsed with:
- Table headers
- Row data
- Optional captions

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Page not found"
}
```

Common errors:
- "Page not found" - Title doesn't exist
- "Rate limit exceeded" - Too many requests (auto-retries with backoff)
- "Missing required parameter" - Invalid function call

## Usage Notes

1. **Title Matching**: Use exact page titles for best results. Use search first to find correct titles.

2. **Rate Limiting**: The Wikipedia API has rate limits. The skill implements automatic retries with exponential backoff.

3. **Chinese Characters**: The skill properly handles Chinese characters in titles and queries. URL encoding is handled automatically.

4. **Large Pages**: Pages with extensive competition records (e.g., Olympic athletes) may return large datasets.

5. **Missing Data**: Not all pages have infoboxes or medal records. Check for null values.

## Examples

### Athlete Research

```json
// Search for athletes
{"function": "search", "query": "马龙 乒乓球", "limit": 3}

// Get detailed data
{"function": "get_page", "title": "马龙 (乒乓球运动员)"}

// Expected medal_summary output:
{
  "奥运会": {"gold": 6, "silver": 0, "bronze": 0},
  "世界锦标赛": {"gold": 14, "silver": 1, "bronze": 4},
  "世界杯": {"gold": 11, "silver": 2, "bronze": 3},
  "合计": {"gold": 31, "silver": 3, "bronze": 7}
}
```

### Biography Summary

```json
// Quick summary
{"function": "get_extract", "title": "张继科", "sentences": 2}

// Full biography data
{"function": "get_page", "title": "张继科"}
```

## Technical Details

- **API Endpoint**: `https://zh.wikipedia.org/w/api.php`
- **User-Agent**: Identifies as SearchOS research bot
- **Timeout**: 30 seconds per request
- **Retries**: Up to 3 attempts with exponential backoff
- **Dependencies**: httpx, beautifulsoup4