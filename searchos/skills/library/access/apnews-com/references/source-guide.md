# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# AP News Access Skill

This skill fetches and extracts structured content from Associated Press (AP) News articles at apnews.com.

## Features

- **Article Extraction**: Retrieves complete article content including:
  - Headline/title
  - Byline and author information (names, titles, contact info)
  - Full article body text
  - Publication and modification dates
  - Keywords and tags
  - Images with dimensions
  - Article section/category

- **Search**: Find articles by keyword or topic

## Functions

### get_article

Fetches a single article and extracts all available structured content.

**Parameters:**
- `url` (required): The AP News article URL

**Example:**
```json
{
  "function": "get_article",
  "url": "https://apnews.com/article/iran-us-hormuz-strait-war-july-21-2026-1664f6a4dad005a99771b2ad15213585"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://apnews.com/article/...",
  "headline": "Article headline",
  "description": "Article description/summary",
  "body": "Full article body text...",
  "body_length": 6191,
  "authors": [
    {
      "name": "Author Name",
      "url": "https://apnews.com/author/...",
      "job_title": "Job Title"
    }
  ],
  "date_published": "2026-07-21T07:44:29Z",
  "date_modified": "2026-07-22T05:47:48Z",
  "keywords": ["keyword1", "keyword2"],
  "section": ["World News"],
  "images": [
    {
      "url": "https://...",
      "width": 980,
      "height": 653
    }
  ],
  "publisher": "AP News",
  "source": "json-ld"
}
```

### search

Searches for AP News articles matching a query.

**Parameters:**
- `query` (required): Search query
- `max_results` (optional): Maximum results to return (default: 10)

**Example:**
```json
{
  "function": "search",
  "query": "iran war",
  "max_results": 5
}
```

**Returns:**
```json
{
  "success": true,
  "query": "iran war",
  "total_results": 5,
  "results": [
    {
      "url": "https://apnews.com/article/...",
      "title": "Article title"
    }
  ],
  "note": "For full article content, use get_article with the URL"
}
```

## Data Sources

The skill extracts data from multiple sources:

1. **JSON-LD Structured Data**: Primary source for metadata (headline, authors, dates, keywords, etc.)
2. **HTML Parsing**: Extracts full article body from `RichTextStoryBody` div elements
3. **Meta Tags**: Fallback for title, description, and other metadata

## Error Handling

Returns structured error messages for:
- Invalid URLs (must be apnews.com)
- HTTP errors (404, 500, etc.)
- Page unavailable errors
- Missing article body (returns warning but still provides metadata)

## Notes

- AP News articles use JSON-LD structured data following the NewsArticle schema
- The article body is not included in JSON-LD, so it's extracted from HTML
- Author information includes names, job titles, and profile URLs when available
- Images include URLs and dimensions when provided in structured data
