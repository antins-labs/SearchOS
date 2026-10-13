# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# lol.qq.com Article Fetcher

Fetches news and article content from the League of Legends China official website (lol.qq.com).

## Overview

This skill retrieves detailed article information from the mobile news detail pages on lol.qq.com. It uses the underlying JSONP API to extract structured data including:

- Article metadata (title, author, publication date, view count)
- Full article content in both HTML and plain text formats
- Embedded images with URLs
- Tags and source information

## Functions

### get_article

Fetches a specific article by its document ID.

**Parameters:**
- `docid` (string, required): The article's document ID

The `docid` can be provided in two formats:
1. Numeric string: `"10255542153636928057"`
2. Full URL: `"https://lol.qq.com/news/detail_m.html?docid=10255542153636928057"`

**Returns:**
```json
{
  "success": true,
  "article": {
    "docid": "10255542153636928057",
    "title": "2025LPL第三赛段常规赛荣誉评选统计结果及明细",
    "author": "英雄联盟赛事公告",
    "author_id": 815,
    "avatar": "https://...",
    "created_at": "2025-09-06 14:49:03",
    "indexed_at": "2025-09-06 14:50:17",
    "source": "tgl",
    "source_id": 10486789,
    "views": 16257,
    "comments": 0,
    "can_comment": true,
    "tags": ["1280", "2037"],
    "cover_image": "//k6.tgl.qq.com/...",
    "url": "https://lol.qq.com/news/detail_m.html?docid=...",
    "content_html": "<div>...</div>",
    "content_text": "Plain text version...",
    "images": [
      {"url": "https://...", "alt": ""}
    ],
    "uuid": "..."
  }
}
```

**Error Response:**
```json
{
  "error": "Error description",
  "error_code": "ERROR_CODE"
}
```

Possible error codes:
- `MISSING_PARAM`: Required docid parameter not provided
- `INVALID_PARAM`: docid format is invalid
- `HTTP_ERROR`: HTTP request failed
- `PARSE_ERROR`: Failed to parse API response
- `API_ERROR`: API returned an error status
- `NO_DATA`: No article data in response
- `TIMEOUT`: Request timed out
- `JSON_ERROR`: JSON parsing failed
- `UNKNOWN_ERROR`: Unexpected error occurred

## Example Usage

### Fetch by document ID
```json
{
  "function": "get_article",
  "docid": "10255542153636928057"
}
```

### Fetch by URL
```json
{
  "function": "get_article",
  "docid": "https://lol.qq.com/news/detail_m.html?docid=10255542153636928057"
}
```

## Technical Details

- **API Endpoint**: `https://apps.game.qq.com/cmc/zmMcnContentInfo`
- **Response Format**: JSONP (parsed automatically)
- **Encoding**: UTF-8
- **Content Types**: News articles, announcements, event reports, match results

The skill handles:
- JSONP response parsing
- HTML to plain text conversion
- Image URL extraction
- Chinese character encoding
- Error handling and recovery

## Content Examples

Articles typically contain:
- LPL (League of Legends Pro League) announcements
- Match results and schedules
- Team and player news
- Game updates and patches
- Event information
- Award announcements (MVP, All-Star teams, etc.)
