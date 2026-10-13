# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Koreaboo Listicle Scraper

This skill extracts structured content from Koreaboo.com listicle articles, which are popular K-pop news and ranking articles.

## Functions

### `fetch_listicle`

Fetches a single listicle article and extracts all list items with their content.

**Parameters:**
- `url` (required): Full URL of the Koreaboo listicle page
- `include_images` (optional): Include image URLs in output (default: true)

**Returns:**
```json
{
  "success": true,
  "url": "https://www.koreaboo.com/lists/...",
  "title": "Article Title",
  "excerpt": "Article subtitle/description",
  "date": "January 22nd, 2018",
  "date_iso": "2018-01-22T09:03:29+00:00",
  "featured_image": "https://...",
  "item_count": 11,
  "items": [
    {
      "number": 1,
      "title": "Hyorin",
      "full_title": "1. Hyorin",
      "paragraphs": ["Paragraph 1 content...", "Paragraph 2 content..."],
      "images": [{"src": "https://...", "alt": "..."}],
      "image_count": 1
    }
  ]
}
```

### `fetch_lists_category`

Discovers listicle articles from the Koreaboo lists category page.

**Parameters:**
- `page` (optional): Page number for pagination (default: 1)

**Returns:**
```json
{
  "success": true,
  "url": "https://www.koreaboo.com/lists/",
  "page": 1,
  "article_count": 10,
  "articles": [
    {
      "title": "Article Title",
      "url": "https://www.koreaboo.com/lists/...",
      "date": "July 14th, 2026",
      "date_iso": "2026-07-14T...",
      "excerpt": "Brief description...",
      "image": "https://..."
    }
  ],
  "pagination": {
    "has_next": true,
    "has_prev": false,
    "next_url": "https://www.koreaboo.com/lists/page/2/",
    "prev_url": null
  }
}
```

## Usage Examples

### Fetch a specific listicle
```json
{
  "function": "fetch_listicle",
  "url": "https://www.koreaboo.com/lists/11-kpop-idols-started-record-labels/"
}
```

### Browse listicles by category page
```json
{
  "function": "fetch_lists_category",
  "page": 1
}
```

### Fetch without images (faster, smaller response)
```json
{
  "function": "fetch_listicle",
  "url": "https://www.koreaboo.com/lists/...",
  "include_images": false
}
```

## Target Content

This skill is optimized for Koreaboo's listicle format, which typically includes:
- Numbered list items (1. Name, 2. Name, etc.)
- Each item has a title, descriptive paragraphs, and often images
- Articles cover K-pop idols, entertainment news, rankings, and trending topics

## Notes

- Uses Playwright browser automation to handle dynamic content loading
- Automatically parses numbered titles (e.g., "1. Hyorin" → number: 1, title: "Hyorin")
- Extracts all paragraphs between list item headings
- Handles various image container formats used by Koreaboo
