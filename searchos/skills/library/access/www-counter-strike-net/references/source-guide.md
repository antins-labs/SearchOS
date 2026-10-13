# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Counter-Strike 2 News Access Skill

This skill fetches news and updates from Counter-Strike 2 (CS2) via the Steam News API.

## Overview

The official Counter-Strike website (www.counter-strike.net) uses a React-based frontend that requires JavaScript rendering to display content. This skill bypasses that requirement by directly accessing the Steam News API, which provides the same news content in structured JSON format.

## Functions

### list_updates

Lists recent Counter-Strike 2 news and updates.

**Parameters:**
- `count` (integer, optional): Number of items to return. Default: 20, Max: 100
- `offset` (integer, optional): Number of items to skip for pagination. Default: 0

**Example:**
```json
{
  "function": "list_updates",
  "count": 10
}
```

**Returns:**
```json
{
  "success": true,
  "total_returned": 10,
  "offset": 0,
  "items": [
    {
      "gid": "1838407329267700",
      "title": "Counter-Strike 2 Update",
      "date": "2025-01-15 10:30:00",
      "timestamp": 1736928600,
      "url": "https://...",
      "author": "jo",
      "content": "[ GAMEPLAY ]\n...",
      "feed_type": 1,
      "is_external_url": true
    }
  ]
}
```

### get_news_entry

Fetches a specific news entry by its GID (Global ID) with full content.

**Parameters:**
- `gid` (string, required): The unique identifier of the news entry

**Example:**
```json
{
  "function": "get_news_entry",
  "gid": "1838407329267700"
}
```

**Returns:**
```json
{
  "success": true,
  "entry": {
    "gid": "1838407329267700",
    "title": "Counter-Strike 2 Update",
    "date": "2025-01-15 10:30:00",
    "timestamp": 1736928600,
    "url": "https://...",
    "author": "jo",
    "content": "Full content text...",
    "feed_type": 1,
    "is_external_url": true
  }
}
```

**Note:** The GID can be found in the URL of news entries on counter-strike.net (e.g., `/newsentry/1838407329267700`) or from the `list_updates` response.

### search_updates

Searches news/updates by title keyword.

**Parameters:**
- `query` (string, required): Search keyword to match in news titles (case-insensitive)
- `count` (integer, optional): Maximum number of results. Default: 10, Max: 50

**Example:**
```json
{
  "function": "search_updates",
  "query": "patch",
  "count": 5
}
```

**Returns:**
```json
{
  "success": true,
  "query": "patch",
  "total_found": 3,
  "items": [...]
}
```

## Data Source

This skill uses the Steam News API (`ISteamNews/GetNewsForApp/v2`) with App ID 730 (Counter-Strike 2). The API provides:

- News items with GID (unique identifier)
- Title and publication date
- Author information
- Full content in BBCode format
- Original URL on Steam community

## Content Format

News content is returned in Steam's BBCode format, which includes:
- `[p]` - Paragraph
- `[list][*]` - Bullet lists
- `[/list]` - End list
- Section headers like `[ GAMEPLAY ]`, `[ MAPS ]`, `[ MISC ]`

## Limitations

- The Steam News API returns up to 100 most recent items
- Older news entries beyond the 100 most recent may not be accessible via `get_news_entry`
- Content is in BBCode format and may need parsing for display

## Common Use Cases

1. **Get latest updates:** Use `list_updates` with default parameters
2. **Paginate through history:** Use `list_updates` with `offset` parameter
3. **Get full update details:** Use `get_news_entry` with GID from list
4. **Find specific updates:** Use `search_updates` with keywords like "patch", "map", "weapon", etc.
