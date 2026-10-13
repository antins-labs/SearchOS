# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Genius.com Annotated Scripts Access Skill

This skill extracts structured content from Genius.com's annotated TV show and movie scripts/transcripts.

## Features

- **Script Content Extraction**: Extracts dialogue blocks, stage directions, and annotated text from script pages
- **Annotation Handling**: Captures annotation references and can optionally fetch annotation details
- **Metadata Extraction**: Retrieves show name, episode title, view counts, and other metadata
- **Search Functionality**: Search for scripts and transcripts on Genius

## Supported Pages

This skill is designed for Genius.com pages containing annotated scripts/transcripts, such as:
- TV show episode scripts (e.g., Game of Thrones, Breaking Bad)
- Movie transcripts
- Annotated screenplays

Example URLs:
- `https://genius.com/Game-of-thrones-winter-is-coming-script-annotated`
- `https://genius.com/Game-of-thrones-a-golden-crown-script-annotated`

## Functions

### get_script

Fetches and extracts the full content of a script/transcript page.

**Parameters:**
- `url` (required): The full Genius.com URL of the script page
- `include_annotations` (optional, default: false): Whether to fetch detailed annotation content

**Returns:**
```json
{
  "url": "https://genius.com/...",
  "title": "Episode Title",
  "show_name": "Show Name",
  "episode_name": "Episode Name",
  "content_blocks": [
    {
      "index": 0,
      "text": "Dialogue or stage direction text",
      "annotations": [
        {"id": "12345", "href": "...", "text": "annotated phrase"}
      ]
    }
  ],
  "full_text": "Complete script text...",
  "annotations": [...],
  "metadata": {...}
}
```

### search

Search for scripts and transcripts on Genius.

**Parameters:**
- `query` (required): Search keywords

**Returns:**
```json
{
  "query": "game of thrones script",
  "search_url": "https://genius.com/search?q=...",
  "results": [
    {"title": "Script Title", "url": "https://genius.com/..."}
  ],
  "count": 5
}
```

### get_metadata

Get metadata about a script page without extracting the full content.

**Parameters:**
- `url` (required): The full Genius.com URL

**Returns:**
```json
{
  "url": "https://genius.com/...",
  "title": "Page Title",
  "description": "Page description",
  "image": "https://...",
  "author": "Show/Author name",
  "tags": [...],
  "stats": {
    "views": "12345",
    "annotations": "42"
  }
}
```

## Important Notes

### Cloudflare Protection

Genius.com uses Cloudflare protection which may occasionally block automated access. The skill includes anti-detection measures but may encounter challenges. If access is blocked:

1. The skill will return an error with `hint` field explaining the situation
2. Try again later - Cloudflare challenges are often temporary
3. Consider using the official Genius API for programmatic access

### Content Structure

Genius script pages typically contain:
- **Title**: The show and episode name
- **Full transcript**: All dialogue and stage directions
- **Annotations**: User-contributed notes on specific lines (highlighted text)
- **Metadata**: View counts, annotation counts, tags

The skill attempts to extract:
1. Full text content from `[data-lyrics-container="true"]` (Genius's standard content container)
2. Structured content blocks for easier parsing
3. Annotation references with IDs and links
4. Metadata from meta tags and JSON-LD structured data

### Rate Limiting

To avoid being blocked:
- Don't make too many requests in quick succession
- Use `get_metadata` when you only need basic info
- Consider caching results locally

## Example Usage

Get full script content:
```json
{
  "function": "get_script",
  "url": "https://genius.com/Game-of-thrones-winter-is-coming-script-annotated",
  "include_annotations": true
}
```

Search for scripts:
```json
{
  "function": "search",
  "query": "breaking bad script"
}
```

Get page metadata only:
```json
{
  "function": "get_metadata",
  "url": "https://genius.com/Game-of-thrones-winter-is-coming-script-annotated"
}
```

## Error Handling

The skill returns structured errors:

```json
{
  "error": "Access blocked by Cloudflare protection",
  "url": "https://genius.com/...",
  "hint": "The site may require human verification. Try again later."
}
```

Common errors:
- `"URL parameter is required"` - Missing required URL parameter
- `"URL must be from genius.com domain"` - Invalid domain
- `"Query parameter is required"` - Missing search query
- `"Unknown function: ..."` - Invalid function name
- `"Access blocked by Cloudflare protection"` - Site blocked automated access
