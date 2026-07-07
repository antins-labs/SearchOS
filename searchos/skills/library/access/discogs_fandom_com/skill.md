# Discogs Fandom Wiki Access Skill

This skill provides access to the Discogs Chinese Fandom Wiki (discogs.fandom.com/zh), 
which contains detailed information about albums, artists, and music releases with 
structured infobox data.

## Overview

The site uses MediaWiki software and provides a standard MediaWiki API endpoint that 
returns structured data about wiki pages. This skill bypasses the Cloudflare protection 
on the web interface by using the API directly.

## Features

### 1. Get Page Content (`get_page`)
Fetches the raw content of a wiki page in wikitext format.

**Parameters:**
- `title` (required): The exact page title

**Returns:**
- `pageid`: Internal page ID
- `title`: Page title
- `url`: Full URL to the page
- `wikitext`: Raw wikitext content

**Example:**
```python
result = await execute({
    "function": "get_page",
    "title": "跨时代 (周杰伦专辑)"
})
```

### 2. Get Album Info (`get_album`)
Fetches structured album information with parsed infobox and tracklist.

**Parameters:**
- `title` (required): The exact album page title

**Returns:**
- `pageid`: Internal page ID
- `title`: Page title
- `url`: Full URL to the page
- `infobox`: Dictionary of album metadata fields including:
  - 专辑名 (Album name)
  - 艺人 (Artist)
  - 类型 (Type)
  - 首发时间 (Release date)
  - 唱片编号 (Catalog number)
  - 唱片公司 (Record company)
  - 厂牌 (Label)
  - ISRC
  - And more...
- `tracks`: List of tracks with track number, title, artist, and notes
- `description`: Brief introduction text

**Example:**
```python
result = await execute({
    "function": "get_album",
    "title": "跨时代 (周杰伦专辑)"
})
# Returns structured album data including:
# - infobox: {专辑名: "跨时代", 艺人: "周杰伦", 首发时间: "2010年05月18日", ...}
# - tracks: [{track_number: 1, title: "跨时代"}, ...]
```

### 3. Search (`search`)
Searches for pages matching a query.

**Parameters:**
- `query` (required): Search terms
- `limit` (optional): Maximum number of results (default: 10)

**Returns:**
- `results`: List of matching pages with pageid, title, snippet, size
- `count`: Number of results

**Example:**
```python
result = await execute({
    "function": "search",
    "query": "周杰伦",
    "limit": 10
})
```

### 4. List Pages (`list_pages`)
Lists pages in the wiki (paginated).

**Parameters:**
- `limit` (optional): Maximum number of results (default: 50)
- `continue` (optional): Pagination cursor from previous result

**Returns:**
- `pages`: List of pages with pageid and title
- `continue`: Cursor for next page (if more results available)

**Example:**
```python
result = await execute({
    "function": "list_pages",
    "limit": 20
})

# Get next page
if result.get("continue"):
    next_result = await execute({
        "function": "list_pages",
        "limit": 20,
        "continue": result["continue"]
    })
```

## Available Data

The wiki contains information about:
- Albums (专辑) with detailed infoboxes
- EPs, singles, and compilations
- Artist discographies
- Release dates, catalog numbers, ISRC codes
- Tracklists with track numbers and notes
- Label and publisher information

## Notes

- Page titles are in Chinese and typically follow the pattern: "专辑名 (艺人专辑)" or "专辑名 (艺人EP)"
- The API returns wikitext which is parsed to extract structured data
- Wiki markup like `[[link]]` and `{{template}}` is cleaned from output
- Some fields may contain wiki templates that are simplified in the output

## Error Handling

All functions return an `error` field when issues occur:
- Page not found
- Invalid parameters
- HTTP errors
- Network timeouts

Example error response:
```json
{
  "error": "Page 'Unknown Album' not found"
}
```