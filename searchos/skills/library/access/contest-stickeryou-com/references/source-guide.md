# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Stickeryou News Review Access Skill

This skill extracts content from the contest.stickeryou.com news site.

## Features

### get_article
Fetches and parses a single article page, extracting:
- Title, author, publication date
- Meta description and featured image
- Article content (headings and paragraphs)
- Table of contents (if present)
- Related posts

**Parameters:**
- `url` (required): Article URL or path (e.g., `/stickeryou-news/article-slug`)

**Example:**
```json
{
  "function": "get_article",
  "url": "https://contest.stickeryou.com/stickeryou-news/new-olympic-sports-since-2000-a-modern-games-evolu"
}
```

### get_news_listing
Fetches a paginated list of news articles.

**Parameters:**
- `page` (optional): Page number, defaults to 1

**Example:**
```json
{
  "function": "get_news_listing",
  "page": 1
}
```

### search_articles
Searches for articles by keyword in titles across multiple listing pages.

**Parameters:**
- `query` (required): Search keyword
- `max_pages` (optional): Maximum pages to scan, defaults to 3

**Example:**
```json
{
  "function": "search_articles",
  "query": "weather",
  "max_pages": 5
}
```

## Notes

- The site uses server-side rendering, so direct HTTP requests work efficiently
- Article content is extracted from the `<article>` element
- Related posts are extracted from sidebar sections
- Pagination follows standard URL pattern: `/news?page=N`
