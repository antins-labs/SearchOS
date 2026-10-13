# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Virgin Atlantic Help Center Article Fetcher

This skill retrieves help articles from Virgin Atlantic's Knowledge Portal at www.virginatlantic.com.

## Features

- **Get Article**: Fetch the full content of a specific help article by URL or article ID
- **Search Articles**: Browse available help articles in the knowledge portal

## Usage

### Get Article by URL

```json
{
  "function": "get_article",
  "url": "https://www.virginatlantic.com/en-BB/help/articles/what-is-my-hand-baggage-allowance----a5a24d4c-a652-4fbd-925d-57d0ead2ed5e"
}
```

### Get Article by ID

```json
{
  "function": "get_article",
  "article_id": "a5a24d4c-a652-4fbd-925d-57d0ead2ed5e",
  "locale": "en-BB"
}
```

### Search Articles

```json
{
  "function": "search_articles",
  "query": "baggage"
}
```

## Response Format

### get_article

```json
{
  "title": "What is my hand baggage allowance?",
  "date": "March 17, 2026",
  "content": "Full article text content...",
  "url": "https://www.virginatlantic.com/en-BB/help/articles/...",
  "success": true
}
```

### search_articles

```json
{
  "articles": [
    {
      "title": "What is my hand baggage allowance?",
      "url": "https://www.virginatlantic.com/en-BB/help/articles/...",
      "article_id": "a5a24d4c-a652-4fbd-925d-57d0ead2ed5e"
    }
  ],
  "total": 10,
  "success": true
}
```

## Technical Notes

- The Virgin Atlantic help center uses Next.js with client-side rendering
- Article content is loaded dynamically after initial page load
- This skill uses Playwright browser automation to extract fully rendered content
- Content extraction includes title, publication date, and main article body
- Footer navigation and non-article content are filtered out

## Supported Locales

Common locale codes include:
- `en-GB` - United Kingdom
- `en-BB` - Barbados
- `en-US` - United States

## Error Handling

Returns an `error` field with description when:
- Invalid URL or article ID provided
- Article content fails to load
- Network or browser errors occur
