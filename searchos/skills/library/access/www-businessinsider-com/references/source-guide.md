# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Business Insider Access Skill

Extracts structured content from Business Insider articles with specialized handling for slideshow/timeline articles.

## Features

- **Full Article Extraction**: Captures title, author, publication date, and all content
- **Slideshow Support**: Automatically detects and extracts all slides from timeline/slideshow articles
- **Image URLs**: Resolves lazy-loaded images to actual CDN URLs
- **Year Extraction**: Automatically identifies years mentioned in timeline content
- **Structured Output**: Returns clean, structured data suitable for analysis

## Functions

### get_article

Extracts complete article content from a Business Insider URL.

**Parameters:**
- `url` (required): Business Insider article URL

**Returns:**
- Article metadata (title, author, dates)
- For slideshow articles: all slides with headings, sources, images, and extracted years
- For regular articles: paragraphs and subheadings

**Example:**
```json
{
  "function": "get_article",
  "url": "https://www.businessinsider.com/olympic-games-when-sports-were-added-timeline-2021-7"
}
```

### get_slideshow

Specifically extracts slideshow/timeline content from Business Insider articles.

**Parameters:**
- `url` (required): Business Insider slideshow article URL

**Returns:**
- Slideshow metadata
- All slides with structured data (heading, source, image URL, year)

**Example:**
```json
{
  "function": "get_slideshow",
  "url": "https://www.businessinsider.com/olympic-games-when-sports-were-added-timeline-2021-7"
}
```

## Output Structure

### Slideshow Article
```json
{
  "success": true,
  "article": {
    "title": "What year every sport was added to the Olympics...",
    "author": "Joey Hadden",
    "date_published": "2021-07-28T20:04:46.000Z",
    "content_type": "slideshow",
    "slide_count": 25,
    "slides": [
      {
        "slide_number": 1,
        "heading": "The Olympic games of 1896 showcased...",
        "source": "Source: International Olympic Committee",
        "image_url": "https://i.insider.com/...",
        "image_alt": "...",
        "year": 1896
      }
    ]
  }
}
```

## Notes

- Uses browser automation to handle JavaScript rendering and lazy-loaded images
- Resolves lazy-loaded image placeholders to actual CDN URLs
- Extracts years from timeline headings automatically
- Handles both slideshow and regular article formats
