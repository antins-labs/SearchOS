# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# NPR.org Access Skill

Fetches articles and section listings from NPR.org with proper metadata extraction.

## Features

- **Article Extraction**: Retrieves full article content including title, author, publication date, body text, and rich metadata from JSON-LD
- **Section Listings**: Lists articles from NPR section pages (e.g., Science, Politics, Health)
- **Robust Parsing**: Handles NPR's consistent article structure for reliable body extraction

## Functions

### get_article

Fetch a single NPR article with complete content extraction.

**Parameters:**
- `url` (required): The NPR article URL

**Returns:**
```json
{
  "success": true,
  "url": "https://www.npr.org/...",
  "title": "Article headline",
  "author": "Author name",
  "date_published": "2020-12-08T10:58:07-05:00",
  "date_display": "DECEMBER 8, 2020",
  "headline": "SEO headline",
  "description": "Article description/summary",
  "body": "Full article body text...",
  "body_paragraphs": ["Paragraph 1", "Paragraph 2", ...],
  "word_count": 500,
  "topic": "Science",
  "story_id": "944152693",
  "images": ["https://media.npr.org/..."]
}
```

### get_section

List articles from an NPR section/topic page.

**Parameters:**
- `url` (optional): The NPR section URL (e.g., https://www.npr.org/sections/science)
- `section` (optional): Section name (e.g., "science", "politics", "health")
- `limit` (optional): Maximum articles to return (default: 20)

**Returns:**
```json
{
  "success": true,
  "section": "Science",
  "url": "https://www.npr.org/sections/science",
  "count": 15,
  "articles": [
    {
      "url": "https://www.npr.org/...",
      "title": "Article title",
      "date": "2024-01-15",
      "topic": "Health",
      "teaser": "Article preview text..."
    }
  ]
}
```

## Usage Examples

### Fetch an Article
```json
{
  "function": "get_article",
  "url": "https://www.npr.org/2020/12/08/944152693/everest-gets-a-growth-spurt-as-china-nepal-revise-offici"
}
```

### List Science Articles
```json
{
  "function": "get_section",
  "section": "science",
  "limit": 10
}
```

### List from Section URL
```json
{
  "function": "get_section",
  "url": "https://www.npr.org/sections/politics"
}
```

## Notes

- Article body is extracted from the `#storytext` element, which contains the main content
- Captions, credits, and byline text are filtered out from the body
- JSON-LD structured data provides additional metadata when available
- The skill handles NPR's URL patterns including both numeric IDs (e.g., /944152693/) and newer format (e.g., /nx-s1-5897484/)
