# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# The Guardian Article Extractor

This skill extracts article content and metadata from The Guardian news website (www.theguardian.com).

## Features

### 1. Article Extraction (`extract_article`)

Extracts comprehensive information from a Guardian article URL:

- **Headline**: Article title
- **Description**: Article summary/standfirst
- **Authors**: List of article authors
- **Section**: News section (e.g., World, Politics, Technology)
- **Tags**: Article tags/topics
- **Published date**: Original publication timestamp (ISO 8601 format)
- **Modified date**: Last modification timestamp (ISO 8601 format)
- **Article text**: Full article body text
- **Word count**: Total word count of the article
- **Publication**: Always "The Guardian"

**Example usage:**
```json
{
  "function": "extract_article",
  "url": "https://www.theguardian.com/world/2005/may/30/france.eu"
}
```

**Response:**
```json
{
  "url": "https://www.theguardian.com/world/2005/may/30/france.eu",
  "headline": "French PM expected to resign",
  "description": "The French prime minister was expected to present his resignation...",
  "authors": ["Guardian staff reporter"],
  "section": "World news",
  "tags": ["World news", "France", "European Union", "Politics", "Europe"],
  "published_date": "2005-05-30T16:26:13.000Z",
  "modified_date": "2017-05-08T06:14:53.000Z",
  "article_text": "The French prime minister was expected to present his resignation...",
  "word_count": 928,
  "publication": "The Guardian"
}
```

### 2. Get Sections (`get_sections`)

Retrieve a list of all available Guardian news sections.

**Example usage:**
```json
{
  "function": "get_sections"
}
```

**Response:**
```json
{
  "sections": [
    {"id": "world", "name": "World news"},
    {"id": "politics", "name": "Politics"},
    {"id": "technology", "name": "Technology"},
    {"id": "environment", "name": "Environment"},
    ...
  ],
  "total": 38
}
```

## Data Sources

The skill extracts data from multiple sources for maximum reliability:

1. **LD+JSON structured data**: Primary source for article metadata (headline, dates, authors, article body)
2. **Open Graph meta tags**: Fallback for description, section, dates
3. **HTML content**: Fallback for article text when LD+JSON is unavailable

## Supported URL Patterns

The skill works with standard Guardian article URLs:
- `https://www.theguardian.com/<section>/<year>/<month>/<day>/<article-slug>`
- `https://www.theguardian.com/<section>/<year>/<month>/<day>/<article-slug>?<params>`

## Error Handling

The skill returns structured error responses:

| Error Code | Description |
|------------|-------------|
| `NOT_FOUND` | Article URL returns 404 or "Page Not Found" |
| `INVALID_URL` | URL is not from www.theguardian.com |
| `MISSING_PARAMETER` | Required parameter not provided |
| `EXTRACTION_ERROR` | Error during content extraction |

## Technical Notes

- Uses browser automation (Playwright) to handle JavaScript-rendered content
- Article text is cleaned to remove non-content elements (social buttons, subscription prompts)
- Dates are returned in ISO 8601 format
- Works with both modern and legacy Guardian article formats

## Limitations

- Requires valid Guardian article URLs (does not support search functionality)
- Some interactive content (embedded tweets, videos, etc.) may not be fully extracted
- Live blog articles may have incomplete text extraction
