# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Museums Association News Article Fetcher

This skill fetches news articles from the Museums Association website (www.museumsassociation.org), specifically from the Museums Journal news section.

## Features

- **get_article**: Fetch a single news article with full structured content
  - Title, author, publication date
  - Full article text content
  - JSON-LD metadata (date published/modified)
  - Category tags and breadcrumbs

- **get_news_listing**: Browse paginated news listings
  - Lists article titles and URLs
  - Pagination information for navigation

## Usage

### Fetch a specific article

```
function: get_article
url: https://www.museumsassociation.org/museums-journal/news/2022/12/caro-howell-appointed-director-general-of-imperial-war-museums/
```

Returns:
```json
{
  "success": true,
  "url": "...",
  "title": "Caro Howell appointed director-general of Imperial War Museums",
  "author": "Eleanor Mills",
  "date": "6 December 2022",
  "date_published": "2022-12-06T15:35:07+00:00",
  "content": "Full article text...",
  "tags": ["News"]
}
```

### Browse news listings

```
function: get_news_listing
page: 1
```

Returns:
```json
{
  "success": true,
  "articles": [
    {
      "url": "https://...",
      "title": "Article title..."
    }
  ],
  "pagination": [...]
}
```

## Notes

- The site does not require JavaScript rendering; content is available via direct HTTP requests
- Cookie consent walls mentioned in initial probes do not block article content
- Article URLs follow the pattern: `/museums-journal/news/YYYY/MM/article-slug/`
- News listings are paginated with URLs: `/museums-journal/news/page/N/`
