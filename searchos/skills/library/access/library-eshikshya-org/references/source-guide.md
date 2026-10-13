# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Kiwix Wikipedia Mirror Access Skill

This skill retrieves Wikipedia article content from a Kiwix offline mirror hosted at `library.eshikshya.org`.

## Overview

Kiwix is an offline reader for web content, commonly used to host Wikipedia mirrors in environments with limited or no internet access. This skill provides structured extraction of Wikipedia articles from such a mirror, including:

- **Article title and summary** - The main heading and first paragraph
- **Infobox data** - Structured metadata from the article's infobox table (biographical data, statistics, etc.)
- **Section content** - All article sections with their text content
- **Internal links** - Links to other Wikipedia articles, properly formatted
- **Categories** - Article categories for navigation

## Functions

### `get_article`

Fetches and parses a Wikipedia article from the Kiwix mirror.

**Parameters:**
- `article_path` (required): The article path within the mirror, e.g., `"A/Al-Mansur_Muhammad"`

**Returns:**
```json
{
  "title": "Al-Mansur Muhammad",
  "url": "http://library.eshikshya.org/kiwix/content/wikipedia_en_all_maxi_2023-05/A/Al-Mansur_Muhammad",
  "summary": "First paragraph of the article...",
  "infobox": {
    "type": "biography",
    "title": "Al-Mansur Muhammad",
    "image": {"src": "...", "alt": "..."},
    "data": {
      "Born": "c. 1366",
      "Died": "1416",
      ...
    }
  },
  "sections": [
    {"title": "Introduction", "level": 0, "content": "...", "links": [...]},
    {"title": "Biography", "level": 2, "content": "...", "links": [...]},
    ...
  ],
  "categories": ["14th-century people", "Ayyubid dynasty", ...]
}
```

### `search`

Searches for articles in the Kiwix mirror (if the mirror supports search).

**Parameters:**
- `query` (required): Search terms
- `limit` (optional): Maximum number of results (default: 10)

**Returns:**
```json
{
  "query": "al-mansur",
  "results": [
    {"title": "Al-Mansur Muhammad", "url": "...", "snippet": "..."},
    {"title": "Al-Mansur Nasir al-Din", "url": "...", "snippet": "..."},
    ...
  ],
  "total": 5
}
```

### `status`

Checks whether the Kiwix service is currently available.

**Returns:**
```json
{
  "status": "online|offline|parked|error",
  "message": "Status description",
  "available": true|false
}
```

## Article Path Format

Wikipedia articles in Kiwix mirrors are typically organized by first letter and article name:
- `"A/Al-Mansur_Muhammad"` - Article about Al-Mansur Muhammad
- `"A/Al-Mansur_Nasir_al-Din"` - Article about Al-Mansur Nasir al-Din
- `"B/Berlin"` - Article about Berlin

Underscores are used in place of spaces in article titles.

## Error Handling

The skill returns structured error responses:

| Error Type | Description |
|------------|-------------|
| `connection_failed` | Cannot connect to the server |
| `http_error` | Server returned an error status code |
| `service_unavailable` | Domain is parked or Kiwix service not running |
| `missing_parameter` | Required parameter not provided |
| `unknown_function` | Invalid function name |

## Current Service Status

**Note:** During testing, the host `library.eshikshya.org` was found to be serving a domain parking page rather than Kiwix content. The skill is designed to:

1. Detect this situation and return an appropriate error
2. Work correctly if/when the Kiwix service is restored
3. Handle both Kiwix-formatted content and standard Wikipedia HTML

## Technical Details

- Uses `aiohttp` for async HTTP requests
- Parses HTML with BeautifulSoup4
- Extracts infobox data from `<table class="infobox">` elements
- Identifies article content in `<div class="mw-parser-output">`
- Converts relative Kiwix links to proper paths

## Example Usage

```python
# Get an article
result = await execute({
    "function": "get_article",
    "article_path": "A/Al-Mansur_Muhammad"
}, ctx)

# Search for articles
result = await execute({
    "function": "search",
    "query": "al-mansur",
    "limit": 5
}, ctx)

# Check service status
result = await execute({
    "function": "status"
}, ctx)
```
