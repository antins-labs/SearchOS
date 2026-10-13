# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Radio Times List Extractor

This skill extracts structured list content from Radio Times articles, including album discographies, ranked TV/movie lists, and similar content.

## Features

- **Album List Extraction**: Parses artist discographies with album names and release years
- **Ranked List Extraction**: Extracts ordered/numbered lists for rankings
- **Generic List Support**: Handles various list formats with H2 section headings
- **Structured Output**: Returns clean, organized data with sections and entries

## Functions

### get_album_list

Extracts album discographies or similar list content from a Radio Times URL.

**Parameters:**
- `url` (required): Full Radio Times article URL

**Returns:**
```json
{
  "success": true,
  "url": "https://www.radiotimes.com/audio/...",
  "title": "Page title",
  "sections": {
    "what_studio_albums_has_artist_released": {
      "heading": "What studio albums has Artist released?",
      "count": 40,
      "entries": [
        {
          "name": "Album Name",
          "year": "1962",
          "full_text": "Album Name (1962)"
        }
      ]
    }
  },
  "metadata": {
    "headline": "Artist albums in order"
  }
}
```

**Example Usage:**
```
Extract Bob Dylan's complete discography from Radio Times
URL: https://www.radiotimes.com/audio/bob-dylan-albums-in-order-full-list-album-releases/
```

### get_page_info

Gets basic page information and structure without full extraction. Useful for previewing what content is available.

**Parameters:**
- `url` (required): Full Radio Times article URL

**Returns:**
```json
{
  "success": true,
  "url": "https://www.radiotimes.com/...",
  "title": "Page title",
  "headline": "Main heading",
  "h2_count": 5,
  "ul_count": 10,
  "ol_count": 2,
  "sections": ["Section 1", "Section 2", ...]
}
```

## Content Types Supported

- **Album Discographies**: Studio albums, live albums, compilations
- **Ranked Lists**: "Best TV shows", "Top movies", etc.
- **Episode Guides**: TV series episode listings
- **Filmographies**: Actor/director film lists

## Data Extraction Patterns

The skill recognizes these common Radio Times article patterns:

1. **H2 + UL structure**: Section heading followed by unordered list
   - Used for album releases, episode lists
   - Parses album name and year from "Name (Year)" format

2. **Ordered lists (OL)**: Numbered rankings
   - Used for "Best of" lists
   - Preserves ranking position

3. **Multiple sections**: Articles with several categorized lists
   - Each H2 heading creates a separate section
   - Maintains section context for entries

## Limitations

- Only works with radiotimes.com URLs
- Requires JavaScript-rendered content may not be fully extracted
- Complex layouts may need manual verification
- Year parsing expects "(YYYY)" format

## Error Handling

Returns structured error responses:
- Invalid URL format
- Network errors/timeouts
- HTTP error codes
- Missing content

All errors include a `success: false` flag and descriptive `error` message.
